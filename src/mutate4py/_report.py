"""Report formatting for the run loop: line-returning formatters plus the two
scan-path report builders. The run loop (`_runner.py`) logs these lines at
its own edge; nothing here logs except `_on_parallel_result`, which is
itself just a formatting call wrapped for use as a worker-thread callback.
"""

import dataclasses
import logging
import os

from mutate4py._coverage import acquire_coverage
from mutate4py._discovery import Site, discover_sites, partition_sites
from mutate4py._manifest_storage import ManifestLocation
from mutate4py._source_loading import _compute_manifest_diff

__all__ = [
    "CoverageSource",
    "OverheadInfo",
    "RunStats",
    "scan_report",
    "scan_report_with_coverage",
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


@dataclasses.dataclass(frozen=True)
class CoverageSource:
    """Where scan-time coverage comes from."""

    cov_cmd: str | None
    lcov_path: str | None
    reuse_coverage: bool
    cwd: str


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
    all_sites: list[Site],
    covered_lines: set[int],
) -> list[str]:
    """Return the "Uncovered mutations:" block's lines, or [] when nothing is uncovered."""
    uncovered = [s for s in all_sites if s.line not in covered_lines]
    if not uncovered:
        return []
    lines = ["Uncovered mutations:"]
    for s in uncovered:
        fid = f" {s.function_id}" if s.function_id else ""
        lines.append(f"  line {s.line} {s.desc}{fid}")
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


def _selection_report_lines(selection_counts: dict[str, int]) -> list[str]:
    """The Test selection summary line, plus a Warning once any Site degraded."""
    degraded = selection_counts.get("degraded", 0)
    lines = [
        f"Test selection: narrowed {selection_counts['narrowed']}, "
        f"static {selection_counts['static']}, degraded {degraded}"
    ]
    if degraded:
        lines.append(
            f"Warning: {degraded} Site(s) had test-context data rejected as incomplete "
            "(named covering tests came from a single shared --cov-context=test session, "
            "which docs/adr/0021 established silently drops every covering test but the "
            "first to reach a shared line) -- their Mutants ran the full test set instead "
            "of the narrowed one. Rebuild the db with --build-test-contexts for sound "
            "narrowing."
        )
    return lines


def _mutation_report_lines(
    counts: dict[str, int],
    survivors: list[Site],
    uncovered_count: int,
    selection_counts: dict[str, int] | None = None,
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
    if selection_counts is not None:
        lines.extend(_selection_report_lines(selection_counts))
    if overhead is not None:
        lines.extend(_overhead_report_lines(overhead.overhead_duration, overhead.baseline_duration))
    if survivors:
        lines.append("")
        lines.append("Survivors:")
        for s in survivors:
            fid = f" {s.function_id}" if s.function_id else ""
            lines.append(f"  line {s.line} {s.desc}{fid}")
    return lines


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
    clean_source, _, manifest_exists, changed_fn_ids, _ = _compute_manifest_diff(source, loc)
    sites = discover_sites(clean_source)
    if manifest_exists:
        changed_count = len([s for s in sites if s.function_id in changed_fn_ids])
    else:
        changed_count = len(sites)
    return sites, changed_count, manifest_exists


def scan_report(
    path: str, source: str, warning_threshold: int, *, manifest_file: bool = False
) -> tuple[list[str], bool]:
    """Return (output_lines, exceeded_threshold) for a --scan run without coverage."""
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


def scan_report_with_coverage(
    path: str,
    source: str,
    warning_threshold: int,
    coverage: CoverageSource,
    *,
    manifest_file: bool = False,
) -> tuple[list[str], bool]:
    """Return (output_lines, exceeded_threshold) for a --scan run with coverage."""
    sites, changed_count, manifest_exists = _scan_manifest_state(path, source, manifest_file=manifest_file)
    total = len(sites)
    covered_lines = acquire_coverage(
        cov_cmd=coverage.cov_cmd,
        lcov_path=coverage.lcov_path,
        reuse=coverage.reuse_coverage,
        cwd=coverage.cwd,
        source_path=os.path.abspath(path),
    )
    covered, uncovered = partition_sites(sites, covered_lines)
    manifest_str = "true" if manifest_exists else "false"
    lines = [
        f"Mutation scan: {path}",
        f"Total mutation sites: {total}",
        f"Covered mutation sites: {covered}",
        f"Uncovered mutation sites: {uncovered}",
        f"Changed mutation sites: {changed_count}",
        f"Manifest exists: {manifest_str}",
    ]
    exceeded = total > warning_threshold
    if exceeded:
        lines.append(f"Warning: {total} mutation sites exceeds threshold {warning_threshold}.")
    return lines, exceeded
