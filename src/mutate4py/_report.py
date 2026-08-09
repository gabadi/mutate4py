"""Report formatting for the run loop: line-returning formatters plus the two
scan-path report builders. The run loop (`_runner.py`) prints these lines at
its own edge; nothing here calls print() except `_on_parallel_result`, which
is itself just a formatting call wrapped for use as a worker-thread callback.
"""

import dataclasses
import os

from mutate4py._coverage import acquire_coverage
from mutate4py._discovery import Site, discover_sites, partition_sites

__all__ = [
    "CoverageSource",
    "RunStats",
    "scan_report",
    "scan_report_with_coverage",
]


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
    """Print a per-mutant progress line in arrival order (called from worker thread)."""
    print(_parallel_progress_line(result))


def _mutation_report_lines(
    counts: dict[str, int],
    survivors: list[Site],
    uncovered_count: int,
    selection_counts: dict[str, int] | None = None,
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
        lines.append(f"Test selection: narrowed {selection_counts['narrowed']}, static {selection_counts['static']}")
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


def scan_report(path: str, source: str, warning_threshold: int) -> tuple[list[str], bool]:
    """Return (output_lines, exceeded_threshold) for a --scan run without coverage."""
    sites = discover_sites(source)
    total = len(sites)
    lines = [
        f"Mutation scan: {path}",
        f"Total mutation sites: {total}",
        f"Changed mutation sites: {total}",
        "Manifest exists: false",
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
) -> tuple[list[str], bool]:
    """Return (output_lines, exceeded_threshold) for a --scan run with coverage."""
    sites = discover_sites(source)
    total = len(sites)
    covered_lines = acquire_coverage(
        cov_cmd=coverage.cov_cmd,
        lcov_path=coverage.lcov_path,
        reuse=coverage.reuse_coverage,
        cwd=coverage.cwd,
        source_path=os.path.abspath(path),
    )
    covered, uncovered = partition_sites(sites, covered_lines)
    lines = [
        f"Mutation scan: {path}",
        f"Total mutation sites: {total}",
        f"Covered mutation sites: {covered}",
        f"Uncovered mutation sites: {uncovered}",
        "Manifest exists: false",
    ]
    exceeded = total > warning_threshold
    if exceeded:
        lines.append(f"Warning: {total} mutation sites exceeds threshold {warning_threshold}.")
    return lines, exceeded
