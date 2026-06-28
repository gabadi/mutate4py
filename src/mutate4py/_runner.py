"""Mutation run loop — F4 core implementation."""

import datetime
import os
import subprocess
import time

from mutate4py._coverage import CoverageError, acquire_coverage
from mutate4py._discovery import Site, apply_mutant, discover_sites, partition_sites
from mutate4py._manifest import (
    build_manifest,
    diff_manifests,
    embed_manifest,
    extract_manifest,
    strip_manifest,
)


def _run_command(cmd: str, cwd: str, timeout: float) -> tuple[str, bool]:
    """Run cmd via shell; return (status, timed_out) where status in {killed,timeout,survived}."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            timeout=timeout,
        )
        return ("survived" if result.returncode == 0 else "killed", False)
    except subprocess.TimeoutExpired:
        return ("timeout", True)


def _baseline_reason(result: subprocess.CompletedProcess) -> str:
    stderr = (result.stderr or b"").decode(errors="replace").strip()
    if stderr:
        return stderr.splitlines()[0]
    return f"exit code {result.returncode}"


def _run_baseline(cmd: str, cwd: str) -> tuple[float, str | None]:
    """Run baseline; return (duration_seconds, error_reason_or_None)."""
    start = time.monotonic()
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True)
    elapsed = time.monotonic() - start
    if result.returncode != 0:
        return elapsed, _baseline_reason(result)
    return elapsed, None


def _filter_by_lines(covered: list[Site], lines_filter: set[int]) -> list[Site]:
    return [s for s in covered if s.line in lines_filter]


def _filter_by_fn(covered: list[Site], changed_fn_ids: set[str]) -> list[Site]:
    return [s for s in covered if s.function_id in changed_fn_ids]


def _select_sites(
    all_sites: list[Site],
    covered_lines: set[int],
    changed_fn_ids: set[str],
    effective_since_last_run: bool,
    lines_filter: set[int] | None,
) -> tuple[list[Site], list[Site]]:
    """Return (covered_sites, selected_sites)."""
    covered = [s for s in all_sites if s.line in covered_lines]
    if lines_filter is not None:
        return covered, _filter_by_lines(covered, lines_filter)
    if effective_since_last_run:
        return covered, _filter_by_fn(covered, changed_fn_ids)
    return covered, covered


def _print_uncovered_block(
    all_sites: list[Site],
    covered_lines: set[int],
) -> None:
    uncovered = [s for s in all_sites if s.line not in covered_lines]
    if not uncovered:
        return
    print("Uncovered mutations:")
    for s in uncovered:
        fid = f" {s.function_id}" if s.function_id else ""
        print(f"  line {s.line} {s.desc}{fid}")


def _restore_from_backup(path: str, bak_path: str) -> str | None:
    """Restore source from backup if present; return rescued source or None."""
    if not os.path.isfile(bak_path):
        return None
    with open(bak_path) as f:
        rescued = f.read()
    with open(path, "w") as f:
        f.write(rescued)
    print("Restored source from backup (previous run was interrupted).")
    with open(path) as f:
        return f.read()


def _compute_manifest_diff(
    source: str,
) -> tuple[str, bool, set[str], str]:
    """Strip manifest, discover sites, diff; return (clean_source, manifest_exists, changed_fn_ids, tested_at)."""
    clean_source = strip_manifest(source)
    existing_manifest, manifest_exists = extract_manifest(source)
    tested_at = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    current_manifest = build_manifest(clean_source, tested_at=tested_at)
    changed_fn_ids = diff_manifests(existing_manifest, current_manifest)
    return clean_source, manifest_exists, changed_fn_ids, tested_at


def _print_run_header(
    path: str,
    total: int,
    covered_count: int,
    uncovered_count: int,
    changed_count: int,
    manifest_exists: bool,
    selected_count: int,
    warning_threshold: int,
) -> None:
    manifest_str = "true" if manifest_exists else "false"
    print(f"Mutation run: {path}")
    print(f"Total mutation sites: {total}")
    print(f"Covered mutation sites: {covered_count}")
    print(f"Uncovered mutation sites: {uncovered_count}")
    print(f"Changed mutation sites: {changed_count}")
    print(f"Manifest exists: {manifest_str}")
    print(f"Selected mutation sites: {selected_count}")
    if total > warning_threshold:
        print(f"Warning: {total} mutation sites exceeds threshold {warning_threshold}.")


def _run_mutation_loop(
    selected_sites: list[Site],
    clean_source: str,
    path: str,
    source_dir: str,
    test_command: str,
    mutant_timeout: float,
) -> tuple[dict, list[Site]]:
    total_selected = len(selected_sites)
    counts: dict[str, int] = {"killed": 0, "timeout": 0, "survived": 0}
    survivors: list[Site] = []
    for i, site in enumerate(selected_sites, 1):
        mutated = apply_mutant(clean_source, site)
        with open(path, "w") as f:
            f.write(mutated)
        status, _ = _run_command(test_command, source_dir, mutant_timeout)
        counts[status] += 1
        if status == "survived":
            survivors.append(site)
        fid_suffix = f": {site.function_id}" if site.function_id else ""
        print(
            f"[{i}/{total_selected}] {status} line {site.line} {site.desc}{fid_suffix}"
        )
    return counts, survivors


def _print_mutation_report(
    counts: dict[str, int],
    survivors: list[Site],
    uncovered_count: int,
) -> None:
    killed_total = counts["killed"] + counts["timeout"]
    print()
    print("Mutation Report")
    print("===============")
    print(f"Killed: {killed_total}")
    print(f"Survived: {counts['survived']}")
    print(f"Uncovered: {uncovered_count}")
    if survivors:
        print()
        print("Survivors:")
        for s in survivors:
            fid = f" {s.function_id}" if s.function_id else ""
            print(f"  line {s.line} {s.desc}{fid}")


def _acquire_covered_lines(
    cov_cmd: str | None,
    lcov_path: str | None,
    reuse_coverage: bool,
    cwd: str,
    abs_source: str,
) -> tuple[set[int] | None, str | None]:
    """Acquire coverage; return (covered_lines, error_message_or_None)."""
    if reuse_coverage:
        print(
            "Reusing existing coverage; covered/uncovered classification may be stale."
        )
    try:
        covered_lines = acquire_coverage(
            cov_cmd=cov_cmd,
            lcov_path=lcov_path,
            reuse=reuse_coverage,
            cwd=cwd,
            source_path=abs_source,
        )
        return covered_lines, None
    except CoverageError as exc:
        return None, str(exc)


def _is_effective_since_last_run(
    since_last_run: bool,
    manifest_exists: bool,
    mutate_all: bool,
    lines_filter: set[int] | None,
) -> bool:
    return since_last_run or (
        manifest_exists and not mutate_all and lines_filter is None
    )


def _print_uncovered_if_needed(
    all_sites: list[Site],
    covered_lines: set[int],
    effective_since_last_run: bool,
    lines_filter: set[int] | None,
) -> None:
    if not effective_since_last_run and lines_filter is None:
        _print_uncovered_block(all_sites, covered_lines)


def _finalize_source(
    path: str, clean_source: str, tested_at: str, bak_path: str
) -> None:
    fresh_manifest = build_manifest(clean_source, tested_at=tested_at)
    with open(path, "w") as f:
        f.write(embed_manifest(clean_source, fresh_manifest))
    if os.path.isfile(bak_path):
        os.remove(bak_path)


def run_mutations(
    *,
    path: str,
    source: str,
    cov_cmd: str | None,
    lcov_path: str | None,
    reuse_coverage: bool,
    test_command: str,
    timeout_factor: int,
    lines_filter: set[int] | None,
    since_last_run: bool,
    mutate_all: bool,
    warning_threshold: int,
    max_workers: int = 0,
    cwd: str,
) -> int:
    """Execute the mutation run loop. Returns exit code (0 or 1)."""
    source_dir = os.path.dirname(os.path.abspath(path))
    bak_path = os.path.join(source_dir, os.path.basename(path) + ".bak")

    rescued = _restore_from_backup(path, bak_path)
    if rescued is not None:
        source = rescued

    clean_source, manifest_exists, changed_fn_ids, tested_at = _compute_manifest_diff(
        source
    )
    all_sites = discover_sites(clean_source)
    changed_count = len([s for s in all_sites if s.function_id in changed_fn_ids])

    covered_lines, cov_error = _acquire_covered_lines(
        cov_cmd, lcov_path, reuse_coverage, cwd, os.path.abspath(path)
    )
    if cov_error is not None:
        print(f"error: {cov_error}")
        return 1

    total = len(all_sites)
    covered_count, uncovered_count = partition_sites(all_sites, covered_lines)
    effective_since_last_run = _is_effective_since_last_run(
        since_last_run, manifest_exists, mutate_all, lines_filter
    )
    covered_sites, selected_sites = _select_sites(
        all_sites, covered_lines, changed_fn_ids, effective_since_last_run, lines_filter
    )

    _print_run_header(
        path,
        total,
        covered_count,
        uncovered_count,
        changed_count,
        manifest_exists,
        len(selected_sites),
        warning_threshold,
    )
    _print_uncovered_if_needed(
        all_sites, covered_lines, effective_since_last_run, lines_filter
    )

    baseline_duration, baseline_error = _run_baseline(test_command, source_dir)
    if baseline_error is not None:
        print(f"baseline failed: {baseline_error}")
        return 1

    with open(bak_path, "w") as f:
        f.write(clean_source)

    mutant_timeout = max(1.0, timeout_factor * baseline_duration)
    counts, survivors = _run_mutation_loop(
        selected_sites, clean_source, path, source_dir, test_command, mutant_timeout
    )

    _finalize_source(path, clean_source, tested_at, bak_path)
    _print_mutation_report(counts, survivors, uncovered_count)
    return 0
