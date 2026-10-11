"""Mutation run loop — F4 core implementation + F6 parallel engine dispatch."""

import dataclasses
import logging
import os

from mutate4py._baseline import measure_per_mutant_overhead, resolve_baseline_and_overhead, run_baseline
from mutate4py._coverage import CoverageError

__all__ = [
    "CoverageError",
    "CoverageSource",
    "NoTestsCollectedError",
    "RunMutationsRequest",
    "TestSelectionError",
    "check_manifest",
    "measure_per_mutant_overhead",
    "run_baseline",
    "run_mutations",
    "run_scan",
    "scan_report",
    "scan_report_with_coverage",
    "update_manifest",
]
from mutate4py._discovery import Site, partition_sites
from mutate4py._equivalent import EquivalentMarkerError, equivalent_markers
from mutate4py._executor import Executor
from mutate4py._executor_selection import select_executor
from mutate4py._exit_codes import EXIT_USAGE, scored_run_exit_code
from mutate4py._execution import (
    ExecutionOutcome,
    MutantExecCtx,
    NoTestsCollectedError,
    TestSelectionError,
    _execute_mutations,
)
from mutate4py._manifest import recorded_survivors
from mutate4py._manifest_modes import check_manifest, update_manifest
from mutate4py._plugin_neutralisation import neutralising_args
from mutate4py._report import (
    _accepted_block_lines,
    CoverageSource,
    RunStats,
    _mutation_report_lines,
    _run_header_lines,
    _workers_header_lines,
    overhead_info,
    scan_report,
    scan_report_with_coverage,
)
from mutate4py._scoring import ScoredRun
from mutate4py._site_selection import (
    _acquire_covered_lines,
    _is_effective_since_last_run,
    _select_sites,
    _should_run_parallel,
    _uncovered_lines_if_needed,
)
from mutate4py._source_loading import (
    RunSetup,
    _finalize_source,
    _prepare_run_setup,
)
from mutate4py._test_dispatch import _log_dispatch_abort

_logger = logging.getLogger(__name__)


@dataclasses.dataclass
class RunMutationsRequest:
    """Everything a mutation run needs: target, coverage source, test invocation,
    selection/execution knobs, and manifest storage.
    """

    path: str
    source: str
    cov_cmd: str | None
    lcov_path: str | None
    reuse_coverage: bool
    pytest_args: list[str]
    timeout_factor: int
    lines_filter: set[int] | None
    since_last_run: bool
    mutate_all: bool
    warning_threshold: int
    cwd: str
    max_workers: int = 0
    min_timeout: float = 1.0
    baseline_duration: float | None = None
    test_contexts_path: str | None = None
    manifest_file: bool = False
    forking_requested: bool = True
    executor: Executor | None = None
    allow_survivors: bool = False


def _print_lines(lines: list[str]) -> None:
    """Log a report block's lines as one call, or nothing when the block is empty."""
    if lines:
        _logger.info("\n".join(lines))


def run_scan(
    *,
    path: str,
    source: str,
    warning_threshold: int,
    coverage: CoverageSource,
    manifest_file: bool = False,
) -> None:
    """Execute --scan: log site counts. Raises CoverageError on acquisition failure."""
    has_coverage = coverage.cov_cmd is not None or coverage.lcov_path is not None or coverage.reuse_coverage
    if has_coverage:
        lines, _ = scan_report_with_coverage(path, source, warning_threshold, coverage, manifest_file=manifest_file)
    else:
        lines, _ = scan_report(path, source, warning_threshold, manifest_file=manifest_file)
    _logger.info("\n".join(lines))


@dataclasses.dataclass
class SelectionOutcome:
    """Result of coverage acquisition, site selection, and mutant-run prep.

    error_code is set (and every other field left at its default) when the run
    must stop early — the caller checks it before touching anything else.
    """

    error_code: int | None = None
    selected_sites: list[Site] = dataclasses.field(default_factory=list)
    covered_lines: set[int] = dataclasses.field(default_factory=set)
    uncovered_count: int = 0
    use_parallel: bool = False
    max_workers: int = 0
    mutant_timeout: float = 0.0
    executor: object = None
    mutant_pytest_args: list[str] = dataclasses.field(default_factory=list)
    baseline_duration: float = 0.0
    overhead_duration: float | None = None
    full_selection: bool = False


@dataclasses.dataclass
class _BaselinePrep:
    """Baseline/overhead/executor cluster, bundled to keep `_select_and_prepare` under the local-count cap."""

    baseline_duration: float
    overhead_duration: float | None
    mutant_timeout: float
    executor: object


def _prepare_baseline_and_executor(
    request: RunMutationsRequest,
    setup: RunSetup,
    mutant_pytest_args: list[str],
    selected_sites: list[Site],
    *,
    use_parallel: bool,
) -> tuple[_BaselinePrep | None, str | None]:
    """Resolve Baseline+overhead, write the backup, compute the timeout, select the executor.

    Returns (prep, baseline_error): prep is None exactly when baseline_error is set.
    """
    baseline_duration, baseline_error, overhead_duration = resolve_baseline_and_overhead(
        request.pytest_args, request.cwd, mutant_pytest_args, request.baseline_duration
    )
    if baseline_error is not None:
        return None, baseline_error

    with open(setup.bak_path, "w") as f:
        f.write(setup.loaded.clean_source)

    mutant_timeout = max(request.min_timeout, request.timeout_factor * baseline_duration)
    executor = select_executor(
        caller_supplied=request.executor,
        use_parallel=use_parallel,
        requested=request.forking_requested and bool(selected_sites),
        cwd=request.cwd,
        guarded_path=os.path.abspath(request.path),
    )

    return _BaselinePrep(baseline_duration, overhead_duration, mutant_timeout, executor), None


def _select_and_prepare(
    request: RunMutationsRequest, setup: RunSetup, test_ctx_db, max_workers: int
) -> SelectionOutcome:
    """Acquire coverage, select sites, print the header, and prepare the executor.

    Returns a SelectionOutcome with error_code set if coverage acquisition or the
    baseline run fails — the caller must check that before using any other field.
    """
    loaded = setup.loaded
    covered_lines, cov_error = _acquire_covered_lines(
        request.cov_cmd,
        request.lcov_path,
        reuse_coverage=request.reuse_coverage,
        cwd=request.cwd,
        abs_source=os.path.abspath(request.path),
    )
    if cov_error is not None:
        # .info, not .error: this single-file path has always written its
        # coverage/baseline failures to stdout (unlike _dispatch.py's directory
        # path, which sends the equivalent messages to stderr) — preserved
        # verbatim rather than "fixed" as a side effect of this migration.
        _logger.info(f"error: {cov_error}")
        return SelectionOutcome(error_code=1)

    covered_count, uncovered_count = partition_sites(loaded.all_sites, covered_lines)
    effective_since_last_run = _is_effective_since_last_run(
        since_last_run=request.since_last_run,
        manifest_exists=loaded.manifest_exists,
        mutate_all=request.mutate_all,
        lines_filter=request.lines_filter,
    )
    _, selected_sites = _select_sites(
        loaded.all_sites,
        covered_lines,
        loaded.changed_fn_ids,
        effective_since_last_run=effective_since_last_run,
        lines_filter=request.lines_filter,
    )

    run_stats = RunStats(
        total=len(loaded.all_sites),
        covered_count=covered_count,
        uncovered_count=uncovered_count,
        changed_count=loaded.changed_count,
        manifest_exists=loaded.manifest_exists,
        selected_count=len(selected_sites),
        warning_threshold=request.warning_threshold,
    )
    _print_lines(_run_header_lines(request.path, run_stats))
    _print_lines(
        _uncovered_lines_if_needed(
            loaded.all_sites,
            covered_lines,
            effective_since_last_run=effective_since_last_run,
            lines_filter=request.lines_filter,
        )
    )

    use_parallel = _should_run_parallel(max_workers, len(selected_sites))
    _print_lines(_workers_header_lines(max_workers, use_parallel=use_parallel, n_selected=len(selected_sites)))

    mutant_pytest_args = [*request.pytest_args, *neutralising_args()]
    prep, baseline_error = _prepare_baseline_and_executor(
        request, setup, mutant_pytest_args, selected_sites, use_parallel=use_parallel
    )
    if baseline_error is not None:
        # .info, not .error: see the matching note on the cov_error branch above.
        _logger.info(f"baseline failed: {baseline_error}")
        return SelectionOutcome(error_code=1)

    return SelectionOutcome(
        selected_sites=selected_sites,
        covered_lines=covered_lines,
        uncovered_count=uncovered_count,
        use_parallel=use_parallel,
        max_workers=max_workers,
        mutant_timeout=prep.mutant_timeout,
        executor=prep.executor,
        mutant_pytest_args=mutant_pytest_args,
        baseline_duration=prep.baseline_duration,
        overhead_duration=prep.overhead_duration,
        full_selection=not effective_since_last_run and request.lines_filter is None,
    )


def _open_test_context_db(test_contexts_path: str | None):
    """Open the test-context db if requested, or None.

    Never clamps max_workers to force serial execution: narrowing composes
    with parallel Workers, so a Test-context db and a Worker count of two or
    more both take effect in the same run.
    """
    if test_contexts_path is None:
        return None
    from mutate4py._test_selection import TestContextDB

    return TestContextDB(test_contexts_path)


def _recorded_survivor_keys(manifest: dict | None) -> frozenset[tuple[str, int, str]]:
    """(function id, line, desc) of every survivor the Manifest held before this run."""
    if manifest is None:
        return frozenset()
    return frozenset((fid, s["line"], s["desc"]) for fid, s in recorded_survivors(manifest))


def _scored_run_for(
    result: ExecutionOutcome, setup: RunSetup, outcome: SelectionOutcome, markers: dict[int, str]
) -> ScoredRun | None:
    """The run's verdicts for scoring, or None when the run errored and records no scores."""
    if result.error_msg is not None:
        return None
    return ScoredRun(
        all_sites=setup.loaded.all_sites,
        covered_lines=outcome.covered_lines,
        selected_sites=outcome.selected_sites,
        survivors=result.survivors,
        markers=markers,
        full_selection=outcome.full_selection,
        recorded_survivors=_recorded_survivor_keys(setup.loaded.existing_manifest),
    )


def _mutant_exec_ctx(request: RunMutationsRequest, outcome: SelectionOutcome, test_ctx_db) -> MutantExecCtx:
    # Parallel Workers compute the plugin kill switches inside their own
    # interpreter (the one that runs pytest); the orchestrator's list is
    # for the serial path only.
    return MutantExecCtx(
        path=request.path,
        cwd=request.cwd,
        pytest_args=request.pytest_args if outcome.use_parallel else outcome.mutant_pytest_args,
        executor=outcome.executor,
        mutant_timeout=outcome.mutant_timeout,
        max_workers=outcome.max_workers,
        use_parallel=outcome.use_parallel,
        abs_source_path=os.path.abspath(request.path),
        test_ctx_db=test_ctx_db,
        forking_requested=request.forking_requested,
    )


def run_mutations(request: RunMutationsRequest) -> int:
    """Execute the mutation run loop.

    Returns 0, 1 (coverage/baseline/worker failure), 2 (selection disagreement or
    usage error), or 3 (the run finished with at least one unaccepted survivor and
    allow_survivors is false).
    """
    test_ctx_db = _open_test_context_db(request.test_contexts_path)
    try:
        setup = _prepare_run_setup(path=request.path, source=request.source, manifest_file=request.manifest_file)
        markers = equivalent_markers(setup.loaded.clean_source)
        outcome = _select_and_prepare(request, setup, test_ctx_db, request.max_workers)
        if outcome.error_code is not None:
            return outcome.error_code

        ctx = _mutant_exec_ctx(request, outcome, test_ctx_db)
        scored_run: ScoredRun | None = None
        try:
            result = _execute_mutations(
                selected_sites=outcome.selected_sites,
                clean_source=setup.loaded.clean_source,
                ctx=ctx,
            )
            scored_run = _scored_run_for(result, setup, outcome, markers)
        finally:
            _finalize_source(
                setup.loaded.clean_source,
                setup.loaded.tested_at,
                setup.bak_path,
                setup.loc,
                existing_manifest=setup.loaded.existing_manifest,
                scored_run=scored_run,
            )
        if result.error_msg is not None:
            # .info, not .error: this has always gone to stdout, same as the
            # cov_error/baseline_error branches in _select_and_prepare above.
            _logger.info(result.error_msg)
            return 1
        _print_lines(
            _mutation_report_lines(
                result.counts,
                scored_run.unaccepted(),
                outcome.uncovered_count,
                result.selection_counts,
                overhead=overhead_info(outcome.overhead_duration, outcome.baseline_duration),
            )
        )
        _print_lines(_accepted_block_lines(scored_run.accepted()))
        return scored_run_exit_code(len(scored_run.unaccepted()), allow_survivors=request.allow_survivors)
    except EquivalentMarkerError as exc:
        _logger.error(f"error: {request.path}: {exc}")
        return EXIT_USAGE
    except (TestSelectionError, NoTestsCollectedError) as exc:
        return _log_dispatch_abort(exc)
    finally:
        if test_ctx_db is not None:
            test_ctx_db.close()
