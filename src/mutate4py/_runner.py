"""Mutation run loop — F4 core implementation."""

import datetime
import os
import subprocess
import time

from mutate4py._coverage import CoverageError, acquire_coverage
from mutate4py._discovery import Site, discover_sites, partition_sites
from mutate4py._manifest import (
    build_manifest,
    diff_manifests,
    embed_manifest,
    extract_manifest,
    strip_manifest,
)
from mutate4py._mutator import apply_mutant


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


def _select_sites(
    all_sites: list[Site],
    covered_lines: set[int],
    changed_fn_ids: set[str],
    effective_since_last_run: bool,
    lines_filter: set[int] | None,
) -> tuple[list[Site], list[Site]]:
    """Return (covered_sites, selected_sites)."""
    covered = [s for s in all_sites if s.line in covered_lines]
    selected = covered
    if lines_filter is not None:
        selected = [s for s in selected if s.line in lines_filter]
    elif effective_since_last_run:
        selected = [s for s in selected if s.function_id in changed_fn_ids]
    return covered, selected


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
    cwd: str,
) -> int:
    """Execute the mutation run loop. Returns exit code (0 or 1)."""
    source_dir = os.path.dirname(os.path.abspath(path))
    bak_path = os.path.join(source_dir, os.path.basename(path) + ".bak")
    abs_source = os.path.abspath(path)

    # Step 1: crash-safety restore
    if os.path.isfile(bak_path):
        with open(bak_path) as f:
            rescued = f.read()
        with open(path, "w") as f:
            f.write(rescued)
        print("Restored source from backup (previous run was interrupted).")
        # Reload source after restore
        with open(path) as f:
            source = f.read()

    # Step 2: strip manifest
    clean_source = strip_manifest(source)

    # Step 3: discover sites, build manifest, diff
    all_sites = discover_sites(clean_source)
    existing_manifest, manifest_exists = extract_manifest(source)
    tested_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    current_manifest = build_manifest(clean_source, tested_at=tested_at)
    changed_fn_ids = diff_manifests(existing_manifest, current_manifest)
    changed_count = len(
        [s for s in all_sites if s.function_id in changed_fn_ids]
    )

    # Step 4: acquire coverage + partition
    if reuse_coverage:
        print("Reusing existing coverage; covered/uncovered classification may be stale.")
    try:
        covered_lines = acquire_coverage(
            cov_cmd=cov_cmd,
            lcov_path=lcov_path,
            reuse=reuse_coverage,
            cwd=cwd,
            source_path=abs_source,
        )
    except CoverageError as exc:
        print(f"error: {exc}")
        return 1

    total = len(all_sites)
    covered_count, uncovered_count = partition_sites(all_sites, covered_lines)

    # Step 5: effectiveSinceLastRun
    effective_since_last_run = since_last_run or (
        manifest_exists and not mutate_all and lines_filter is None
    )

    # Step 6: select sites
    covered_sites, selected_sites = _select_sites(
        all_sites, covered_lines, changed_fn_ids, effective_since_last_run, lines_filter
    )

    # Step 7: print header
    manifest_str = "true" if manifest_exists else "false"
    print(f"Mutation run: {path}")
    print(f"Total mutation sites: {total}")
    print(f"Covered mutation sites: {covered_count}")
    print(f"Uncovered mutation sites: {uncovered_count}")
    print(f"Changed mutation sites: {changed_count}")
    print(f"Manifest exists: {manifest_str}")
    print(f"Selected mutation sites: {len(selected_sites)}")
    if total > warning_threshold:
        print(f"Warning: {total} mutation sites exceeds threshold {warning_threshold}.")

    # Step 8: uncovered block (only when NOT differential and no --lines)
    if not effective_since_last_run and lines_filter is None:
        _print_uncovered_block(all_sites, covered_lines)

    # Step 9: baseline
    baseline_duration, baseline_error = _run_baseline(test_command, source_dir)
    if baseline_error is not None:
        print(f"baseline failed: {baseline_error}")
        return 1

    # Step 10: save backup
    with open(bak_path, "w") as f:
        f.write(clean_source)

    # Step 11: per-site mutation loop
    total_selected = len(selected_sites)
    counts = {"killed": 0, "timeout": 0, "survived": 0}
    survivors: list[Site] = []
    mutant_timeout = max(1.0, timeout_factor * baseline_duration)

    for i, site in enumerate(selected_sites, 1):
        mutated = apply_mutant(clean_source, site)
        with open(path, "w") as f:
            f.write(mutated)
        status, _ = _run_command(test_command, source_dir, mutant_timeout)
        counts[status] += 1
        if status == "survived":
            survivors.append(site)
        fid_suffix = f": {site.function_id}" if site.function_id else ""
        print(f"[{i}/{total_selected}] {status} line {site.line} {site.desc}{fid_suffix}")

    # Step 12: restore source, embed manifest, remove backup
    fresh_manifest = build_manifest(clean_source, tested_at=tested_at)
    restored = embed_manifest(clean_source, fresh_manifest)
    with open(path, "w") as f:
        f.write(restored)
    if os.path.isfile(bak_path):
        os.remove(bak_path)

    # Step 13: print report
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

    return 0
