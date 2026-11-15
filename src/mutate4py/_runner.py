"""Mutation run loop — F4 core implementation + F6 parallel engine dispatch."""

import dataclasses
import logging
import os
from collections.abc import Sequence

__all__ = [
    "NoTestsCollectedError",
    "RunMutationsRequest",
    "check_manifest",
    "run_mutations",
    "run_scan",
    "scan_report",
    "update_manifest",
]
from mutate4py._discovery import Site, partition_sites
from mutate4py._equivalent import EquivalentMarkerError, equivalent_markers
from mutate4py._executor_selection import select_executor
from mutate4py._exit_codes import EXIT_USAGE, scored_run_exit_code
from mutate4py._execution import (
    ExecutionOutcome,
    MutantExecCtx,
    NoTestsCollectedError,
    _execute_mutations,
)
from mutate4py._fresh_digests import fresh_digests
from mutate4py._manifest import recorded_survivors
from mutate4py._manifest_modes import check_manifest, update_manifest
from mutate4py._measurement import ALL, CoverageCoreRefused, Measurement, MeasurementFailed, measure_in_scratch
from mutate4py._plugin_neutralisation import neutralising_args
from mutate4py._report import (
    _accepted_block_lines,
    RunStats,
    SelectionTally,
    _mutation_report_lines,
    _recorded_block_lines,
    _run_header_lines,
    _workers_header_lines,
    executor_block_lines,
    measurement_failure,
    measurement_lines,
    overhead_info,
    scan_report,
)
from mutate4py._run_request import RunMutationsRequest
from mutate4py._scoring import ScoredRun
from mutate4py._skipped_run import recorded_survivors_kept
from mutate4py._site_selection import (
    _is_differential,
    _select_sites,
    _should_run_parallel,
    _uncovered_lines_if_needed,
)
from mutate4py._source_loading import (
    RunSetup,
    _finalize_source,
    _prepare_run_setup,
    apply_digest_changes,
)
from mutate4py._test_dispatch import TimeoutPolicy, _log_dispatch_abort

_logger = logging.getLogger(__name__)


def _print_lines(lines: list[str]) -> None:
    """Log a report block's lines as one call, or nothing when the block is empty."""
    if lines:
        _logger.info("\n".join(lines))


def run_scan(
    *,
    path: str,
    source: str,
    warning_threshold: int,
    manifest_file: bool = False,
) -> None:
    """Execute --scan: log site counts. Coverage-free: no Measurement runs."""
    lines, _ = scan_report(path, source, warning_threshold, manifest_file=manifest_file)
    _logger.info("\n".join(lines))


@dataclasses.dataclass
class SelectionOutcome:
    """Result of the Measurement, site selection, and mutant-run prep.

    error_code is set (and every other field left at its default) when the run
    must stop early — the caller checks it before touching anything else.
    """

    error_code: int | None = None
    selected_sites: list[Site] = dataclasses.field(default_factory=list)
    covered_lines: set[int] = dataclasses.field(default_factory=set)
    uncovered_count: int = 0
    use_parallel: bool = False
    max_workers: int = 0
    timeout_policy: TimeoutPolicy | None = None
    executor: object = None
    mutant_pytest_args: list[str] = dataclasses.field(default_factory=list)
    baseline_duration: float = 0.0
    overhead_duration: float | None = None
    full_selection: bool = False
    measurement: Measurement | None = None
    fresh_digests: dict[str, str] | None = None


@dataclasses.dataclass
class _BaselinePrep:
    """Baseline/overhead/executor cluster, bundled to keep `_select_and_prepare` under the local-count cap."""

    baseline_duration: float
    overhead_duration: float
    timeout_policy: TimeoutPolicy
    executor: object


def _run_measurement(request: RunMutationsRequest, abs_source: str) -> Measurement:
    """The Measurement this run is gated and baselined on: the one handed in, else one taken now."""
    if request.measurement is not None:
        return request.measurement
    return measure_in_scratch(cwd=request.cwd, pytest_args=request.pytest_args, target_files=(abs_source,))


def _prepare_baseline_and_executor(
    request: RunMutationsRequest,
    setup: RunSetup,
    measurement: Measurement,
    selected_sites: list[Site],
    *,
    use_parallel: bool,
) -> _BaselinePrep:
    """Take the Baseline and overhead from the Measurement, write the backup, set the timeout, pick the executor."""
    with open(setup.bak_path, "w") as f:
        f.write(setup.loaded.clean_source)

    timeout_policy = TimeoutPolicy(
        factor=request.timeout_factor,
        min_timeout=request.min_timeout,
        overhead=measurement.per_mutant_overhead,
        budget_of=lambda node_ids: measurement.budget_of(ALL if node_ids is None else node_ids),
    )
    # A run with nothing selected never forks, and the Executor line says why: the user's --no-fork
    # first, else the empty selection.
    no_fork_reason = None
    if not request.forking_requested:
        no_fork_reason = "--no-fork"
    elif not selected_sites:
        no_fork_reason = "no Mutants selected"
    # A caller-supplied executor is used as-is, never re-primed: the caller owns it
    # (a fake in tests, or one primed by a longer-lived caller).
    executor = request.executor
    # A parallel run primes one Executor per Worker, in that Worker's own process (issue 04b).
    if executor is None and not use_parallel:
        executor = select_executor(
            no_fork_reason=no_fork_reason,
            cwd=request.cwd,
            guarded_path=os.path.abspath(request.path),
            pytest_args=request.pytest_args,
            ran_at_import=measurement.empty_lines(os.path.abspath(request.path)),
        )

    return _BaselinePrep(measurement.wall, measurement.per_mutant_overhead, timeout_policy, executor)


def _select_and_prepare(request: RunMutationsRequest, setup: RunSetup, max_workers: int) -> SelectionOutcome:
    """Gate the run's Mutants on the Measurement's covered lines (Empty context included),
    select sites, print the header, and prepare the executor.

    Returns a SelectionOutcome with error_code set if the Measurement fails — the caller
    must check that before using any other field.
    """
    abs_source = os.path.abspath(request.path)
    try:
        measurement = _run_measurement(request, abs_source)
    except (MeasurementFailed, CoverageCoreRefused) as exc:
        code, message = measurement_failure(exc)
        # .info, not .error: this single-file path has always written its
        # baseline failures to stdout (unlike _dispatch.py's directory
        # path, which sends the equivalent messages to stderr) — preserved
        # verbatim rather than "fixed" as a side effect of this migration.
        _logger.info(message)
        return SelectionOutcome(error_code=code)
    covered_lines = set(measurement.covered_lines(abs_source))
    # The digests read the Measurement, not the Mutants, so they are taken before any Site is selected: a function
    # whose stored tests digest moved joins the changed set and is selected like any changed function (#106).
    digests = fresh_digests(measurement, abs_source, setup.loaded.clean_source)
    apply_digest_changes(setup.loaded, digests)

    covered_count, uncovered_count = partition_sites(setup.loaded.all_sites, covered_lines)
    differential = _is_differential(manifest_exists=setup.loaded.manifest_exists)
    _, selected_sites = _select_sites(
        setup.loaded.all_sites,
        covered_lines,
        setup.loaded.changed_fn_ids,
        differential=differential,
    )

    run_stats = RunStats(
        total=len(setup.loaded.all_sites),
        covered_count=covered_count,
        uncovered_count=uncovered_count,
        changed_count=setup.loaded.changed_count,
        manifest_exists=setup.loaded.manifest_exists,
        selected_count=len(selected_sites),
        warning_threshold=request.warning_threshold,
    )
    _print_lines(_run_header_lines(request.path, run_stats))
    _print_lines(
        _uncovered_lines_if_needed(
            setup.loaded.all_sites,
            covered_lines,
            differential=differential,
        )
    )

    use_parallel = _should_run_parallel(max_workers, len(selected_sites))
    _print_lines(_workers_header_lines(max_workers, use_parallel=use_parallel, n_selected=len(selected_sites)))

    prep = _prepare_baseline_and_executor(request, setup, measurement, selected_sites, use_parallel=use_parallel)

    return SelectionOutcome(
        selected_sites=selected_sites,
        covered_lines=covered_lines,
        uncovered_count=uncovered_count,
        use_parallel=use_parallel,
        max_workers=max_workers,
        timeout_policy=prep.timeout_policy,
        executor=prep.executor,
        mutant_pytest_args=[*request.pytest_args, *neutralising_args()],
        baseline_duration=prep.baseline_duration,
        overhead_duration=prep.overhead_duration,
        full_selection=not differential,
        measurement=measurement,
        fresh_digests=digests,
    )


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
        unscored_fn_ids=frozenset(setup.loaded.unscored_fn_ids),
    )


def _mutant_exec_ctx(
    request: RunMutationsRequest, outcome: SelectionOutcome, markers: dict[int, str] | None = None
) -> MutantExecCtx:
    # Parallel Workers compute the plugin kill switches inside their own
    # interpreter (the one that runs pytest); the orchestrator's list is
    # for the serial path only.
    return MutantExecCtx(
        path=request.path,
        cwd=request.cwd,
        pytest_args=request.pytest_args if outcome.use_parallel else outcome.mutant_pytest_args,
        executor=outcome.executor,
        timeout_policy=outcome.timeout_policy,
        max_workers=outcome.max_workers,
        use_parallel=outcome.use_parallel,
        abs_source_path=os.path.abspath(request.path),
        # The Measurement selects: it names the tests that reached each line (issue #96).
        selection_source=outcome.measurement,
        forking_requested=request.forking_requested,
        positionals=outcome.measurement.positional_args,
        ran_at_import=outcome.measurement.empty_lines(os.path.abspath(request.path)),
        # The full set, with the plugin kill switches the orchestrator's serial path also runs under.
        confirm_args=outcome.mutant_pytest_args,
        markers=markers or {},
    )


def _close_executor(executor: object) -> None:
    """Stop the executor this run selected if it holds a process (the fork server).

    A caller-supplied executor is the caller's to close.
    """
    close = getattr(executor, "close", None)
    if close is not None:
        close()


def run_mutations(request: RunMutationsRequest) -> int:
    """Execute the mutation run loop.

    Returns 0, 1 (baseline/worker failure), 2 (no test ran for a Mutant or
    usage error), or 3 (the run finished with at least one unaccepted survivor and
    allow_survivors is false).
    """
    try:
        return _run_loop(request)
    except EquivalentMarkerError as exc:
        _logger.error(f"error: {request.path}: {exc}")
        return EXIT_USAGE
    except NoTestsCollectedError as exc:
        return _log_dispatch_abort(exc)


def _run_loop(request: RunMutationsRequest) -> int:
    """Select, execute and finalize the run, then report it. Errors propagate to run_mutations."""
    setup = _prepare_run_setup(
        path=request.path,
        source=request.source,
        manifest_file=request.manifest_file,
        cwd=request.cwd,
        pytest_args=request.pytest_args,
    )
    markers = equivalent_markers(setup.loaded.clean_source)
    outcome = _select_and_prepare(request, setup, request.max_workers)
    if outcome.error_code is not None:
        return outcome.error_code

    ctx = _mutant_exec_ctx(request, outcome, markers)
    scored_run: ScoredRun | None = None
    try:
        result = _execute_mutations(
            selected_sites=outcome.selected_sites,
            clean_source=setup.loaded.clean_source,
            ctx=ctx,
        )
        scored_run = _scored_run_for(result, setup, outcome, markers)
    finally:
        if request.executor is None:
            _close_executor(outcome.executor)
        written = _finalize_source(
            setup.loaded.clean_source,
            setup.loaded.tested_at,
            setup.bak_path,
            setup.loc,
            existing_manifest=setup.loaded.existing_manifest,
            scored_run=scored_run,
            fresh_digests=outcome.fresh_digests,
            fingerprint=setup.fingerprint,
        )
    if result.error_msg is not None:
        # .info, not .error: this has always gone to stdout, like the cov_error branch above.
        _logger.info(result.error_msg)
        return 1
    recorded = recorded_survivors_kept(written, scored_run)
    return _report_run(request, outcome, result, scored_run, recorded=recorded)


def _report_run(
    request: RunMutationsRequest,
    outcome,
    result,
    scored_run: ScoredRun,
    recorded: Sequence[tuple[str, dict]] = (),
) -> int:
    """Print the run's report block and return its exit code.

    recorded holds the survivors the Manifest kept on functions this run did not re-score (#106). They print
    apart from this run's Survivors and count toward the exit code the same way.
    """
    # A run handed its Measurement is one file of a batch: the caller prints the
    # Measurement and overhead lines once for the whole batch.
    measured_here = request.measurement is None
    overhead = overhead_info(outcome.overhead_duration, outcome.baseline_duration) if measured_here else None
    selection = None
    if result.selection_counts is not None:
        selection = SelectionTally(result.selection_counts)
    _print_lines(
        _mutation_report_lines(
            result.counts,
            scored_run.unaccepted(),
            outcome.uncovered_count,
            selection=selection,
            overhead=overhead,
        )
        + executor_block_lines(result.executor_description, result.timing)
    )
    _print_lines(_recorded_block_lines(recorded))
    if request.timing_sink is not None:
        request.timing_sink.merge(result.timing)
    if measured_here and outcome.measurement is not None:
        _print_lines(measurement_lines(outcome.measurement))
    _print_lines(_accepted_block_lines(scored_run.accepted()))
    survived = len(scored_run.unaccepted()) + len(recorded)
    return scored_run_exit_code(survived, allow_survivors=request.allow_survivors)
