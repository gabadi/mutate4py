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
from mutate4py._test_dispatch import TestSelectionError, _build_mutant_args

__all__ = ["MutantExecCtx", "TestSelectionError"]

_logger = logging.getLogger(__name__)


@dataclasses.dataclass
class MutantExecCtx:
    """Where and how mutants are executed for one run: paths, executor, timeout, and dispatch mode."""

    path: str
    cwd: str
    pytest_args: list[str]
    executor: Executor | None
    mutant_timeout: float
    max_workers: int = 0
    use_parallel: bool = False
    abs_source_path: str = ""
    test_ctx_db: object = None
    forking_requested: bool = True


def _run_mutation_loop(
    selected_sites: list[Site],
    clean_source: str,
    ctx: MutantExecCtx,
) -> tuple[dict, list[Site], dict[str, int] | None]:
    """Run each selected site through ctx.executor; the third return is the
    narrowed/static tally, or None when no context db is in play. Raises
    TestSelectionError on a selection disagreement.

    ctx.executor is always primed by the time this loop starts (whichever
    implementation _prepare_executor chose), so this loop never branches on
    which one it has — it only ever calls executor.run(args, timeout).
    """
    total_selected = len(selected_sites)
    counts: dict[str, int] = {"killed": 0, "timeout": 0, "survived": 0}
    selection_counts: dict[str, int] = {"narrowed": 0, "static": 0}
    survivors: list[Site] = []
    for i, site in enumerate(selected_sites, 1):
        # Built before the splice so a disagreement aborts with the source untouched.
        args, selection = _build_mutant_args(ctx.pytest_args, ctx.test_ctx_db, ctx.abs_source_path, site)
        if selection is not None:
            selection_counts[selection] += 1
        mutated = apply_mutant(clean_source, site)
        with open(ctx.path, "w") as f:
            f.write(mutated)
        status = ctx.executor.run(args, ctx.mutant_timeout)
        counts[status] += 1
        if status == "survived":
            survivors.append(site)
        _logger.info(_serial_progress_line(i, total_selected, status, site))
    return counts, survivors, (selection_counts if ctx.test_ctx_db is not None else None)


def _run_parallel_workers(
    selected_sites: list[Site],
    clean_source: str,
    ctx: MutantExecCtx,
) -> tuple[dict | None, list[Site] | None, dict[str, int] | None, str | None]:
    """Dispatch the parallel engine; return (counts, survivors, selection_counts, error_msg).

    A TestSelectionError raised inside a Worker's dispatch propagates
    uncaught, same as the serial loop — only WorkerFailureError/ParallelRunError
    (real dispatch-mechanics failures) are translated into an error message here.
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
                mutant_timeout=ctx.mutant_timeout,
                max_workers=ctx.max_workers,
                on_result=_on_parallel_result,
                test_ctx_db=ctx.test_ctx_db,
                abs_source_path=ctx.abs_source_path,
                forking_requested=ctx.forking_requested,
                executor=ctx.executor,
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
    from the serial loop propagates to the caller, which must still finalize
    the source exactly as a completed run would leave it.
    """
    if ctx.use_parallel:
        counts, survivors, selection_counts, error_msg = _run_parallel_workers(selected_sites, clean_source, ctx)
        if error_msg is not None:
            return ExecutionOutcome(error_msg=error_msg)
        return ExecutionOutcome(counts=counts, survivors=survivors, selection_counts=selection_counts)
    counts, survivors, selection_counts = _run_mutation_loop(selected_sites, clean_source, ctx)
    return ExecutionOutcome(counts=counts, survivors=survivors, selection_counts=selection_counts)
