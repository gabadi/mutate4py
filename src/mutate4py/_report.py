"""Report formatting for the run loop: line-returning formatters plus the two
scan-path report builders. The run loop (`_runner.py`) logs these lines at
its own edge; nothing here logs except `_on_parallel_result`, which is
itself just a formatting call wrapped for use as a worker-thread callback.
"""

import dataclasses
import logging

from mutate4py._discovery import Site, discover_sites
from mutate4py._executor import ExecutorDescription, MutantTiming
from mutate4py._exit_codes import EXIT_FAILURE, EXIT_USAGE
from mutate4py._manifest_storage import ManifestLocation
from mutate4py._measurement import CoverageCoreRefused, Measurement, MeasurementFailed
from mutate4py._source_loading import _compute_manifest_diff
from mutate4py._test_dispatch import NO_TESTS_HINT

__all__ = [
    "OverheadInfo",
    "RunStats",
    "batch_summary_lines",
    "measurement_failure",
    "measurement_lines",
    "overhead_info",
    "scan_report",
]

_logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class RunStats:
    """Site counts printed in the run header."""

    total: int
    covered_count: int
    uncovered_count: int
    changed_count: int
    manifest_exists: bool
    selected_count: int
    warning_threshold: int


def _run_header_lines(path: str, stats: RunStats) -> list[str]:
    manifest_str = "true" if stats.manifest_exists else "false"
    lines = [
        f"Mutation run: {path}",
        f"Total mutation sites: {stats.total}",
        f"Covered mutation sites: {stats.covered_count}",
        f"Uncovered mutation sites: {stats.uncovered_count}",
        f"Changed mutation sites: {stats.changed_count}",
        f"Manifest exists: {manifest_str}",
        f"Selected mutation sites: {stats.selected_count}",
    ]
    if stats.total > stats.warning_threshold:
        lines.append(f"Warning: {stats.total} mutation sites exceeds threshold {stats.warning_threshold}.")
    return lines


def _uncovered_block_lines(
    path: str,
    sites_in_scope: list[Site],
    covered_lines: set[int],
) -> list[str]:
    uncovered = [s for s in sites_in_scope if s.line not in covered_lines]
    if not uncovered:
        return []
    lines = ["Uncovered mutations:"]
    for s in uncovered:
        fid = f" {s.function_id}" if s.function_id else ""
        lines.append(f"  {path}:{s.line} {s.desc}{fid}")
    return lines


def _serial_progress_line(i: int, total_selected: int, status: str, site: Site) -> str:
    fid_suffix = f": {site.function_id}" if site.function_id else ""
    return f"[{i}/{total_selected}] {status} line {site.line} {site.desc}{fid_suffix}"


def _parallel_progress_line(result: dict) -> str:
    site = result["site"]
    site_idx = result["site_idx"]
    total = result["total"]
    worker_idx = result["worker_idx"]
    status = result["status"]
    fid_suffix = f": {site.function_id}" if site.function_id else ""
    return f"[{site_idx}/{total}] worker-{worker_idx} {status} line {site.line} {site.desc}{fid_suffix}"


def _on_parallel_result(result: dict) -> None:
    """Log a per-mutant progress line in arrival order (called from worker thread)."""
    _logger.info(_parallel_progress_line(result))


# Overhead at or above this share of the Baseline's own duration means a
# Mutant spends more of its run on fixed cost than on the tests it exists to
# run — the threshold, not the measured value, is what tests pin.
_OVERHEAD_HINT_RATIO = 0.5


@dataclasses.dataclass(frozen=True)
class OverheadInfo:
    """Per-Mutant overhead paired with the Baseline duration it was measured
    alongside — bundled into one param so _mutation_report_lines stays at
    the project's 5-argument cap."""

    overhead_duration: float
    baseline_duration: float


def overhead_info(overhead_duration: float | None, baseline_duration: float | None) -> OverheadInfo | None:
    """Pair a run's Per-Mutant overhead with its Baseline, or None when the run
    reports no overhead of its own — a run handed a Measurement leaves the
    overhead line to its batch, which prints it once for every file.
    """
    if overhead_duration is None:
        return None
    return OverheadInfo(overhead_duration, baseline_duration)


def _overhead_report_lines(overhead_duration: float, baseline_duration: float) -> list[str]:
    """The per-Mutant overhead line, plus a plugin-audit hint once overhead
    reaches _OVERHEAD_HINT_RATIO of the Baseline it was measured alongside.
    """
    lines = [f"Per-Mutant overhead: {overhead_duration:.2f}s"]
    if baseline_duration > 0 and overhead_duration / baseline_duration >= _OVERHEAD_HINT_RATIO:
        lines.append(
            "Hint: per-Mutant overhead is high relative to your test suite; "
            "audit pytest plugins with --pytest-args (e.g. -p no:<plugin>)."
        )
    return lines


def measurement_lines(measurement: Measurement) -> list[str]:
    """The Measurement line, plus the coverage.py core note when the core is the slow pytrace one.

    Opens with a blank line so the Survivors block above it ends there: the
    Measurement's wall time varies run to run and is not part of that block.
    """
    lines = ["", f"Measurement: {measurement.wall:.2f}s, {measurement.tests} tests, core {measurement.core}"]
    if measurement.note is not None:
        lines.append(measurement.note)
    return lines


def batch_summary_lines(measurement: Measurement, timing: MutantTiming, wall: float) -> list[str]:
    """A directory run's closing lines: the Measurement and Per-Mutant overhead, then the Time line
    summed over every file and the run's total wall time (Measurement included), printed once."""
    return [
        *measurement_lines(measurement),
        *_overhead_report_lines(measurement.per_mutant_overhead, measurement.wall),
        timing.render(),
        f"Wall: {wall:.2f}s",
    ]


def measurement_failure(exc: MeasurementFailed | CoverageCoreRefused) -> tuple[int, str]:
    """The exit code and error line for a run whose Measurement gave it no Baseline."""
    if isinstance(exc, CoverageCoreRefused):
        return EXIT_USAGE, f"error: {exc}"
    if exc.no_tests:
        return EXIT_FAILURE, f"error: {exc}: {NO_TESTS_HINT}"
    return EXIT_FAILURE, f"error: {exc}"


@dataclasses.dataclass(frozen=True)
class SelectionTally:
    """A run's narrowed and static Mutant counts, as the Measurement selected them."""

    counts: dict[str, int]


def _selection_report_lines(selection: SelectionTally) -> list[str]:
    """The Test selection summary line: Mutants narrowed to their covering tests, and Mutants run on the full set."""
    counts = selection.counts
    return [f"Test selection: narrowed {counts['narrowed']}, static {counts['static']}"]


def _mutation_report_lines(
    counts: dict[str, int],
    survivors: list[Site],
    uncovered_count: int,
    selection: SelectionTally | None = None,
    overhead: OverheadInfo | None = None,
) -> list[str]:
    killed_total = counts["killed"] + counts["timeout"]
    lines = [
        "",
        "Mutation Report",
        "===============",
        f"Killed: {killed_total}",
        f"Survived: {counts['survived']}",
        f"Uncovered: {uncovered_count}",
    ]
    if selection is not None:
        lines.extend(_selection_report_lines(selection))
    if overhead is not None:
        lines.extend(_overhead_report_lines(overhead.overhead_duration, overhead.baseline_duration))
    if survivors:
        lines.append("")
        lines.append("Survivors:")
        for s in survivors:
            fid = f" {s.function_id}" if s.function_id else ""
            lines.append(f"  line {s.line} {s.desc}{fid}")
    return lines


def _accepted_block_lines(accepted: list[tuple[Site, str]]) -> list[str]:
    """One line per accepted survivor with its equivalent reason. Empty when none."""
    if not accepted:
        return []
    lines = ["", "Accepted equivalents:"]
    for s, reason in accepted:
        fid = f" {s.function_id}" if s.function_id else ""
        lines.append(f"  line {s.line} {s.desc}{fid} (equivalent: {reason})")
    return lines


def _module_level_block_lines(path: str, survivors: list[Site]) -> list[str]:
    module_level = [s for s in survivors if not s.function_id]
    if not module_level:
        return []
    return [
        "",
        "Module-level survivors (not recorded in the Manifest):",
        *[f"  {path}:{s.line} {s.desc}" for s in module_level],
    ]


def _closing_block_lines(path: str, unaccepted: list[Site], accepted: list[tuple[Site, str]]) -> list[str]:
    return _accepted_block_lines(accepted) + _module_level_block_lines(path, unaccepted)


def _recorded_block_lines(recorded: list[tuple[str, dict]]) -> list[str]:
    """The survivors a skipped function kept from the Manifest, apart from this run's Survivors (#106).

    Each entry is (function id, {"line", "desc"}). Empty when none.
    """
    if not recorded:
        return []
    lines = ["", "Recorded survivors (function unchanged, not re-run):"]
    for fid, s in recorded:
        lines.append(f"  line {s['line']} {s['desc']} {fid}")
    return lines


def executor_block_lines(description: ExecutorDescription, timing: MutantTiming) -> list[str]:
    """The Time and Executor lines that close a run's Mutation Report, blank-led to sit apart from Survivors."""
    return ["", timing.render(), f"Executor: {description.render()}"]


def _workers_header_lines(max_workers: int, *, use_parallel: bool, n_selected: int) -> list[str]:
    if max_workers <= 0:
        return []
    displayed = min(max_workers, n_selected) if use_parallel else max_workers
    return [f"Mutation workers: {displayed}"]


def _scan_manifest_state(path: str, source: str, *, manifest_file: bool) -> tuple[list[Site], int, bool]:
    """Sites discovered on the manifest-stripped source, plus changed-site count
    and manifest-exists.

    changed_fn_ids (from the same per-function diff the real run selects with)
    only ever contains named-function ids, so a site outside any function
    never matches it — with no special case, a module-level-only file would
    report Changed=0 even on an untracked first scan. Since "no manifest" means
    nothing has a prior baseline to diff against, every site counts as changed
    in that case; once a manifest exists, changed_fn_ids drives the real diff.
    """
    loc = ManifestLocation(path=path, manifest_file=manifest_file)
    diff = _compute_manifest_diff(source, loc)
    sites = discover_sites(diff.clean_source)
    if diff.manifest_exists:
        changed_count = len([s for s in sites if s.function_id in diff.changed_fn_ids])
    else:
        changed_count = len(sites)
    return sites, changed_count, diff.manifest_exists


def scan_report(
    path: str, source: str, warning_threshold: int, *, manifest_file: bool = False
) -> tuple[list[str], bool]:
    """Return (output_lines, exceeded_threshold) for a --scan run: coverage-free."""
    sites, changed_count, manifest_exists = _scan_manifest_state(path, source, manifest_file=manifest_file)
    total = len(sites)
    manifest_str = "true" if manifest_exists else "false"
    lines = [
        f"Mutation scan: {path}",
        f"Total mutation sites: {total}",
        f"Changed mutation sites: {changed_count}",
        f"Manifest exists: {manifest_str}",
    ]
    exceeded = total > warning_threshold
    if exceeded:
        lines.append(f"Warning: {total} mutation sites exceeds threshold {warning_threshold}.")
    return lines, exceeded
