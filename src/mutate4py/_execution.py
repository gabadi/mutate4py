"""Mutant execution engine for the run loop: builds each mutant's test
command, runs it (serial loop, forking executor, or parallel workers), and tallies
counts/survivors. Nothing here writes the manifest or logs a final report —
callers own both; the one log call left is per-mutant progress feedback,
using line formatters `_report` already owns.
"""

import dataclasses
import logging

from mutate4py._discovery import Site, apply_mutant
from mutate4py._executor import Executor
from mutate4py._report import _on_parallel_result, _serial_progress_line
from mutate4py._test_dispatch import (
    NoTestsCollectedError,
    PlanInputs,
    TestSelectionError,
    TimeoutPolicy,
    _check_execution_status,
    plan_mutant,
)

__all__ = ["MutantExecCtx", "NoTestsCollectedError", "TestSelectionError"]

_logger = logging.getLogger(__name__)


@dataclasses.dataclass
class MutantExecCtx:
    """Where and how mutants are executed for one run: paths, executor, timeout, and dispatch mode."""

    path: str
    cwd: str
    pytest_args: list[str]
    executor: Executor | None
    timeout_policy: TimeoutPolicy
    max_workers: int = 0
    use_parallel: bool = False
    abs_source_path: str = ""
    selection_source: object = None  # the Measurement, or the --test-contexts db; None selects nothing
    forking_requested: bool = True
    positionals: tuple[str, ...] = ()


def _run_mutation_loop(
    selected_sites: list[Site],
    clean_source: str,
    ctx: MutantExecCtx,
) -> tuple[dict, list[Site], dict[str, int] | None]:
    """Run each selected site through ctx.executor; the third return is the
    narrowed/static/degraded tally, or None when no selection source is in play.
    Raises TestSelectionError on a selection disagreement, or
    NoTestsCollectedError if a mutant's test run exercised no test at all.

    ctx.executor is always primed by the time this loop starts (whichever
    implementation _prepare_executor chose), so this loop never branches on
    which one it has — it only ever calls executor.run(args, timeout).
    """
    total_selected = len(selected_sites)
    counts: dict[str, int] = {"killed": 0, "timeout": 0, "survived": 0}
    selection_counts: dict[str, int] = {"narrowed": 0, "static": 0, "degraded": 0}
    survivors: list[Site] = []
    plan_inputs = PlanInputs(
        pytest_args=ctx.pytest_args,
        selection_source=ctx.selection_source,
        abs_source_path=ctx.abs_source_path,
        timeout_policy=ctx.timeout_policy,
        positionals=ctx.positionals,
    )
    for i, site in enumerate(selected_sites, 1):
        # Planned before the splice so a disagreement aborts with the source untouched.
        plan = plan_mutant(site, plan_inputs)
        if plan.selection is not None:
            selection_counts[plan.selection] += 1
        mutated = apply_mutant(clean_source, site)
        with open(ctx.path, "w") as f:
            f.write(mutated)
        status = ctx.executor.run(plan.args, plan.timeout)
        # Raises before tallying: a Mutant pytest never exercised must never
        # reach the tally as `killed` (issue #55). The splice already
        # happened, but the caller's finally block restores the source.
        _check_execution_status(status, ctx.abs_source_path, site)
        counts[status] += 1
        if status == "survived":
            survivors.append(site)
        _logger.info(_serial_progress_line(i, total_selected, status, site))
    return counts, survivors, (selection_counts if ctx.selection_source is not None else None)


def _run_parallel_workers(
    selected_sites: list[Site],
    clean_source: str,
    ctx: MutantExecCtx,
) -> tuple[dict | None, list[Site] | None, dict[str, int] | None, str | None]:
    """Dispatch the parallel engine; return (counts, survivors, selection_counts, error_msg).

    A TestSelectionError or NoTestsCollectedError raised inside a Worker's
    dispatch propagates uncaught, same as the serial loop — only
    WorkerFailureError/ParallelRunError (real dispatch-mechanics failures)
    are translated into an error message here.
    """
    from mutate4py._workers import ParallelRunError, ParallelRunRequest, WorkerFailureError, run_parallel

    try:
        counts, survivors, selection_counts = run_parallel(
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
                executor=ctx.executor,
                positionals=ctx.positionals,
            )
        )
        return counts, survivors, selection_counts, None
    except WorkerFailureError as e:
        return None, None, None, f"mutation worker failed: {e}"
    except ParallelRunError as e:
        return None, None, None, str(e)


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


def _execute_mutations(
    *,
    selected_sites: list[Site],
    clean_source: str,
    ctx: MutantExecCtx,
) -> ExecutionOutcome:
    """Run serial or parallel mutations; return counts/survivors.

    The caller owns the final report and error output. A TestSelectionError
    or NoTestsCollectedError from the serial loop propagates to the caller,
    which must still finalize the source exactly as a completed run would
    leave it.
    """
    if ctx.use_parallel:
        counts, survivors, selection_counts, error_msg = _run_parallel_workers(selected_sites, clean_source, ctx)
        if error_msg is not None:
            return ExecutionOutcome(error_msg=error_msg)
        return ExecutionOutcome(counts=counts, survivors=survivors, selection_counts=selection_counts)
    counts, survivors, selection_counts = _run_mutation_loop(selected_sites, clean_source, ctx)
    return ExecutionOutcome(counts=counts, survivors=survivors, selection_counts=selection_counts)
