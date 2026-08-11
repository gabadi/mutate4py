"""Mutation run loop — F4 core implementation + F6 parallel engine dispatch."""

import dataclasses
import datetime
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
from mutate4py._executor import Executor
from mutate4py._executor_selection import select_executor
from mutate4py._execution import MutantExecCtx, NoTestsCollectedError, TestSelectionError, _execute_mutations
from mutate4py._manifest import (
    build_manifest,
    manifests_structurally_equal,
    reconcile_manifest,
    source_sha256,
    strip_manifest,
)
from mutate4py._manifest_storage import (
    ManifestLocation,
    _read_existing_manifest,
    _write_manifest_output,
)
from mutate4py._plugin_neutralisation import neutralising_args
from mutate4py._report import (
    CoverageSource,
    OverheadInfo,
    RunStats,
    _mutation_report_lines,
    _run_header_lines,
    _workers_header_lines,
    scan_report,
    scan_report_with_coverage,
)
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


def update_manifest(*, path: str, source: str, manifest_file: bool = False) -> int:
    """Execute --update-manifest: refresh the manifest in its configured storage. Returns exit code."""
    loc = ManifestLocation(path=path, manifest_file=manifest_file)
    existing, _ = _read_existing_manifest(source, loc)
    clean = strip_manifest(source)
    tested_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    candidate = build_manifest(clean, tested_at=tested_at)
    manifest_to_embed = reconcile_manifest(existing, candidate)
    manifest_changed = manifest_to_embed is not existing

    if manifest_file:
        source_has_stale_footer = clean != source
        if not manifest_changed and not source_has_stale_footer:
            _logger.info(f"Manifest unchanged: {path}")
            return 0
        _write_manifest_output(
            clean,
            manifest_to_embed,
            loc,
            write_source=source_has_stale_footer,
            write_manifest=manifest_changed,
        )
        _logger.info(f"Updated manifest: {path}")
        return 0

    if not manifest_changed:
        _logger.info(f"Manifest unchanged: {path}")
        return 0
    _write_manifest_output(clean, manifest_to_embed, loc)
    _logger.info(f"Updated manifest: {path}")
    return 0


def check_manifest(*, path: str, source: str, manifest_file: bool = False) -> int:
    """Check if the manifest in its configured storage is up to date. Returns 0 if current, 1 if stale or missing."""
    clean = strip_manifest(source)
    loc = ManifestLocation(path=path, manifest_file=manifest_file)
    existing, manifest_exists = _read_existing_manifest(source, loc)
    if not manifest_exists:
        _logger.info(f"Manifest missing: {path}")
        return 1
    existing_source_sha256 = existing.get("source_sha256")
    if existing_source_sha256 is not None and existing_source_sha256 == source_sha256(clean):
        _logger.info(f"Manifest current: {path}")
        return 0
    tested_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    candidate = build_manifest(clean, tested_at=tested_at)
    if manifests_structurally_equal(existing, candidate):
        _logger.info(f"Manifest current: {path}")
        return 0
    _logger.info(f"Manifest stale: {path}")
    return 1


@dataclasses.dataclass
class SelectionOutcome:
    """Result of coverage acquisition, site selection, and mutant-run prep.

    error_code is set (and every other field left at its default) when the run
    must stop early — the caller checks it before touching anything else.
    """

    error_code: int | None = None
    selected_sites: list[Site] = dataclasses.field(default_factory=list)
    uncovered_count: int = 0
    use_parallel: bool = False
    max_workers: int = 0
    mutant_timeout: float = 0.0
    executor: object = None
    mutant_pytest_args: list[str] = dataclasses.field(default_factory=list)
    baseline_duration: float = 0.0
    overhead_duration: float | None = None


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
        uncovered_count=uncovered_count,
        use_parallel=use_parallel,
        max_workers=max_workers,
        mutant_timeout=prep.mutant_timeout,
        executor=prep.executor,
        mutant_pytest_args=mutant_pytest_args,
        baseline_duration=prep.baseline_duration,
        overhead_duration=prep.overhead_duration,
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


def run_mutations(request: RunMutationsRequest) -> int:
    """Execute the mutation run loop.

    Returns 0, 1 (coverage/baseline failure), or 2 (the test-context db and the
    LCOV coverage disagree about a selected site, or a selected site's test run
    exercised no test at all).
    """
    test_ctx_db = _open_test_context_db(request.test_contexts_path)
    try:
        setup = _prepare_run_setup(path=request.path, source=request.source, manifest_file=request.manifest_file)
        outcome = _select_and_prepare(request, setup, test_ctx_db, request.max_workers)
        if outcome.error_code is not None:
            return outcome.error_code

        ctx = MutantExecCtx(
            path=request.path,
            cwd=request.cwd,
            pytest_args=outcome.mutant_pytest_args,
            executor=outcome.executor,
            mutant_timeout=outcome.mutant_timeout,
            max_workers=outcome.max_workers,
            use_parallel=outcome.use_parallel,
            abs_source_path=os.path.abspath(request.path),
            test_ctx_db=test_ctx_db,
            forking_requested=request.forking_requested,
        )
        try:
            result = _execute_mutations(
                selected_sites=outcome.selected_sites,
                clean_source=setup.loaded.clean_source,
                ctx=ctx,
            )
        finally:
            _finalize_source(
                setup.loaded.clean_source,
                setup.loaded.tested_at,
                setup.bak_path,
                setup.loc,
                existing_manifest=setup.loaded.existing_manifest,
            )
        if result.error_msg is not None:
            # .info, not .error: this has always gone to stdout, same as the
            # cov_error/baseline_error branches in _select_and_prepare above.
            _logger.info(result.error_msg)
            return 1
        overhead = (
            OverheadInfo(outcome.overhead_duration, outcome.baseline_duration)
            if outcome.overhead_duration is not None
            else None
        )
        _print_lines(
            _mutation_report_lines(
                result.counts,
                result.survivors,
                outcome.uncovered_count,
                result.selection_counts,
                overhead=overhead,
            )
        )
        return 0
    except (TestSelectionError, NoTestsCollectedError) as exc:
        return _log_dispatch_abort(exc)
    finally:
        if test_ctx_db is not None:
            test_ctx_db.close()
