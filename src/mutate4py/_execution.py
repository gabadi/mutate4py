"""Mutant execution engine for the run loop: builds each mutant's test
command, runs it (serial loop, forking executor, or parallel workers), and tallies
counts/survivors. Nothing here writes the manifest or logs a final report —
callers own both; the one log call left is per-mutant progress feedback,
using line formatters `_report` already owns.
"""

import dataclasses
import logging
import time
from typing import TYPE_CHECKING

from mutate4py._discovery import Site, apply_mutant
from mutate4py._executor import Executor, ExecutorDescription, MutantTiming
from mutate4py._report import _on_parallel_result, _serial_progress_line
from mutate4py._subprocess_executor import SubprocessExecutor
from mutate4py._test_dispatch import (
    ControlRuns,
    ControlTarget,
    NoTestsCollectedError,
    PlanInputs,
    SurvivorConfirmation,
    TimeoutPolicy,
    confirm_plan,
    confirm_survivors,
    plan_mutant,
)

__all__ = ["MutantExecCtx", "NoTestsCollectedError"]

if TYPE_CHECKING:
    from mutate4py._workers import ParallelRunResult

_logger = logging.getLogger(__name__)


@dataclasses.dataclass
class MutantExecCtx:
    """Where and how mutants are executed for one run: paths, executor, timeout, and dispatch mode."""

    path: str
    cwd: str
    pytest_args: list[str]
    executor: Executor
    timeout_policy: TimeoutPolicy
    max_workers: int = 0
    use_parallel: bool = False
    worker_executor: Executor | None = None
    abs_source_path: str = ""
    selection_source: object = None  # the Measurement; None selects nothing
    forking_requested: bool = True
    positionals: tuple[str, ...] = ()
    # The guarded file's lines the Measurement saw run at import, which swap mode refuses to swap.
    ran_at_import: frozenset[int] = frozenset()
    # The full test set's argv (plugin kill switches included); equivalent markers, whose lines are
    # never confirmed; and the timing, filled in as the Mutants and confirmations execute.
    confirm_args: list[str] = dataclasses.field(default_factory=list)
    markers: dict[int, str] = dataclasses.field(default_factory=dict)
    timing: MutantTiming = dataclasses.field(default_factory=MutantTiming)


def _run_mutation_loop(
    selected_sites: list[Site],
    clean_source: str,
    ctx: MutantExecCtx,
) -> tuple[dict, list[Site], dict[str, int] | None]:
    """Run each selected site through ctx.executor; the third return is the
    narrowed/static tally, or None when no selection source is in play.
    Raises NoTestsCollectedError if a mutant's test run exercised no test at all.

    ctx.executor is always primed by the time this loop starts (whichever
    implementation _prepare_executor chose), so this loop never branches on
    which one it has — it only ever calls executor.run(args, timeout).

    A Mutant whose pytest exits 4 or 5 gets a Control run on the original code
    (`ControlRuns`): killed if tests run there, an abort if they do not.
    """
    total_selected = len(selected_sites)
    counts: dict[str, int] = {"killed": 0, "timeout": 0, "survived": 0}
    selection_counts: dict[str, int] = {"narrowed": 0, "static": 0}
    survivors: list[Site] = []
    plan_inputs = PlanInputs(
        pytest_args=ctx.pytest_args,
        selection_source=ctx.selection_source,
        abs_source_path=ctx.abs_source_path,
        timeout_policy=ctx.timeout_policy,
        positionals=ctx.positionals,
        cwd=ctx.cwd,
    )
    controls = ControlRuns()
    target = ControlTarget(ctx.path, clean_source, ctx.executor, ctx.abs_source_path)
    for i, site in enumerate(selected_sites, 1):
        # Planned before the splice so a disagreement aborts with the source untouched.
        plan = plan_mutant(site, plan_inputs)
        if plan.selection is not None:
            selection_counts[plan.selection] += 1
        mutated = apply_mutant(clean_source, site)
        with open(ctx.path, "w") as f:
            f.write(mutated)
        started = time.monotonic()
        status = ctx.executor.run(plan.args, plan.timeout)
        elapsed = time.monotonic() - started
        # Raises before tallying: a Mutant pytest never exercised must never
        # reach the tally as `killed` (issue #55). The splice already
        # happened, but the caller's finally block restores the source.
        status = controls.settle(status, plan, site, target)
        counts[status] += 1
        ctx.timing.record(status, elapsed)
        if status == "survived":
            survivors.append(site)
        _logger.info(_serial_progress_line(i, total_selected, status, site))
    return counts, survivors, (selection_counts if ctx.selection_source is not None else None)


def _run_parallel_workers(
    selected_sites: list[Site],
    clean_source: str,
    ctx: MutantExecCtx,
) -> "tuple[ParallelRunResult | None, str | None]":
    """Dispatch the parallel engine; return (result, error_msg), one of them None.

    A NoTestsCollectedError raised inside a Worker's
    dispatch propagates uncaught, same as the serial loop — only
    WorkerFailureError/ParallelRunError (real dispatch-mechanics failures)
    are translated into an error message here.
    """
    from mutate4py._workers import ParallelRunError, ParallelRunRequest, WorkerFailureError, run_parallel

    try:
        result = run_parallel(
            ParallelRunRequest(
                selected_sites=selected_sites,
                clean_source=clean_source,
                source_path=ctx.path,
                cwd=ctx.cwd,
                pytest_args=ctx.pytest_args,
                timeout_policy=ctx.timeout_policy,
                max_workers=ctx.max_workers,
                on_result=_on_parallel_result,
                selection_source=ctx.selection_source,
                abs_source_path=ctx.abs_source_path,
                forking_requested=ctx.forking_requested,
                executor=ctx.worker_executor,
                positionals=ctx.positionals,
                ran_at_import=ctx.ran_at_import,
                confirmation=_confirmation_in_clones(ctx),
            )
        )
        return result, None
    except WorkerFailureError as e:
        return None, f"mutation worker failed: {e}"
    except ParallelRunError as e:
        return None, str(e)


@dataclasses.dataclass
class ExecutionOutcome:
    """Result of running mutations: counts/survivors on success, or an error message.

    error_msg is set (and counts/survivors/selection_counts left at their
    defaults) when the parallel engine failed before producing a tally — the
    caller checks it before using the other fields.
    """

    counts: dict[str, int] | None = None
    survivors: list[Site] | None = None
    selection_counts: dict[str, int] | None = None
    error_msg: str | None = None
    confirmation_runs: int = 0
    confirmation_kills: int = 0
    timing: MutantTiming | None = None
    executor_description: ExecutorDescription | None = None


def _confirm_survivors(
    survivors: list[Site],
    clean_source: str,
    ctx: MutantExecCtx,
    executor: Executor,
) -> tuple[list[Site], int, int]:
    """Re-run each Survivor with the full test set; return (still surviving, runs, kills)."""
    confirmation = SurvivorConfirmation(confirm_plan(ctx.confirm_args, ctx.timeout_policy), ctx.markers)
    target = ControlTarget(ctx.path, clean_source, executor, ctx.abs_source_path)
    result = confirm_survivors(survivors, target, confirmation, ctx.timing)
    return result.still, result.runs, result.kills


def _on_fork_server(executor: Executor) -> bool:
    return executor.describe().file_mode == "fresh import"


def _confirmation_executor(ctx: MutantExecCtx) -> Executor:
    if _on_fork_server(ctx.executor):
        return ctx.executor
    return SubprocessExecutor(ctx.cwd, ctx.abs_source_path)


def _confirmation_in_clones(ctx: MutantExecCtx) -> SurvivorConfirmation | None:
    if _on_fork_server(ctx.executor):
        return None
    return SurvivorConfirmation(confirm_plan(ctx.confirm_args, ctx.timeout_policy), ctx.markers)


def _execute_mutations(
    *,
    selected_sites: list[Site],
    clean_source: str,
    ctx: MutantExecCtx,
) -> ExecutionOutcome:
    """Run serial or parallel mutations, then confirm their Survivors; return counts/survivors.

    A fresh-imported guarded file's Survivors are confirmed on the orchestrator's
    fork server, for a serial and a parallel run alike. Any other file's are
    confirmed in a fresh interpreter: a serial run through the subprocess
    executor, a parallel run by each Worker in its own clone. The caller owns
    the final report and error output. A
    NoTestsCollectedError from the serial loop propagates to the caller,
    which must still finalize the source exactly as a completed run would
    leave it.
    """
    confirmed = None
    if ctx.use_parallel:
        parallel, error_msg = _run_parallel_workers(selected_sites, clean_source, ctx)
        if parallel is None:
            return ExecutionOutcome(error_msg=error_msg)
        counts, survivors, selection_counts = parallel.counts, parallel.survivors, parallel.selection_counts
        ctx.timing.merge(parallel.timing)
        description = parallel.executor_description
        confirmed = parallel.confirmation
    else:
        counts, survivors, selection_counts = _run_mutation_loop(selected_sites, clean_source, ctx)
        description = ctx.executor.describe()
    if confirmed is None:
        survivors, runs, kills = _confirm_survivors(survivors, clean_source, ctx, _confirmation_executor(ctx))
    else:
        survivors, runs, kills = confirmed.still, confirmed.runs, confirmed.kills
    counts["killed"] += kills
    counts["survived"] -= kills
    return ExecutionOutcome(
        counts=counts,
        survivors=survivors,
        selection_counts=selection_counts,
        confirmation_runs=runs,
        confirmation_kills=kills,
        timing=ctx.timing,
        executor_description=description,
    )
