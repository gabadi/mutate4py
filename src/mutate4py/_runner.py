"""Mutation run loop — F4 core implementation + F6 parallel engine dispatch."""

import datetime
import os
import subprocess
import time

from mutate4py._cmd import run_command as _run_command
from mutate4py._coverage import CoverageError, acquire_coverage

__all__ = [
    "CoverageError",
    "check_manifest",
    "run_mutations",
    "run_scan",
    "scan_report",
    "scan_report_with_coverage",
    "update_manifest",
]
from mutate4py._discovery import Site, apply_mutant, discover_sites, partition_sites
from mutate4py._manifest import (
    build_manifest,
    diff_manifests,
    embed_manifest,
    extract_manifest,
    manifests_structurally_equal,
    strip_manifest,
)


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


def _on_parallel_result(result: dict) -> None:
    """Print a per-mutant progress line in arrival order (called from worker thread)."""
    site = result["site"]
    site_idx = result["site_idx"]
    total = result["total"]
    worker_idx = result["worker_idx"]
    status = result["status"]
    fid_suffix = f": {site.function_id}" if site.function_id else ""
    print(
        f"[{site_idx}/{total}] worker-{worker_idx} {status} line {site.line} {site.desc}{fid_suffix}"
    )


def _run_parallel_workers(
    selected_sites: list[Site],
    clean_source: str,
    path: str,
    cwd: str,
    test_command: str,
    mutant_timeout: float,
    max_workers: int,
) -> tuple[dict | None, list[Site] | None, str | None]:
    """Dispatch the parallel engine; return (counts, survivors, error_msg)."""
    from mutate4py._workers import ParallelRunError, WorkerFailureError, run_parallel

    try:
        counts, survivors = run_parallel(
            selected_sites=selected_sites,
            clean_source=clean_source,
            source_path=path,
            cwd=cwd,
            test_command=test_command,
            mutant_timeout=mutant_timeout,
            max_workers=max_workers,
            on_result=_on_parallel_result,
        )
        return counts, survivors, None
    except WorkerFailureError as e:
        return None, None, f"mutation worker failed: {e}"
    except ParallelRunError as e:
        return None, None, str(e)


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


def _print_workers_header(
    max_workers: int, use_parallel: bool, n_selected: int
) -> None:
    if max_workers > 0:
        displayed = min(max_workers, n_selected) if use_parallel else max_workers
        print(f"Mutation workers: {displayed}")


def _execute_mutations(
    *,
    selected_sites: list[Site],
    clean_source: str,
    path: str,
    source_dir: str,
    cwd: str,
    test_command: str,
    mutant_timeout: float,
    max_workers: int,
    use_parallel: bool,
    tested_at: str,
    bak_path: str,
    uncovered_count: int,
) -> int:
    """Run serial or parallel mutations, finalize source, print report. Returns exit code."""
    if use_parallel:
        counts, survivors, error_msg = _run_parallel_workers(
            selected_sites,
            clean_source,
            path,
            cwd,
            test_command,
            mutant_timeout,
            max_workers,
        )
        _finalize_source(path, clean_source, tested_at, bak_path)
        if error_msg is not None:
            print(error_msg)
            return 1
    else:
        counts, survivors = _run_mutation_loop(
            selected_sites, clean_source, path, source_dir, test_command, mutant_timeout
        )
        _finalize_source(path, clean_source, tested_at, bak_path)
    _print_mutation_report(counts, survivors, uncovered_count)
    return 0


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


def _should_run_parallel(max_workers: int, n_selected: int) -> bool:
    return max_workers >= 2 and n_selected >= 2


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


def scan_report(
    path: str, source: str, warning_threshold: int
) -> tuple[list[str], bool]:
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
        lines.append(
            f"Warning: {total} mutation sites exceeds threshold {warning_threshold}."
        )
    return lines, exceeded


def scan_report_with_coverage(
    path: str,
    source: str,
    warning_threshold: int,
    *,
    cov_cmd: str | None,
    lcov_path: str | None,
    reuse_coverage: bool,
    cwd: str,
) -> tuple[list[str], bool]:
    """Return (output_lines, exceeded_threshold) for a --scan run with coverage."""
    sites = discover_sites(source)
    total = len(sites)
    covered_lines = acquire_coverage(
        cov_cmd=cov_cmd,
        lcov_path=lcov_path,
        reuse=reuse_coverage,
        cwd=cwd,
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
        lines.append(
            f"Warning: {total} mutation sites exceeds threshold {warning_threshold}."
        )
    return lines, exceeded


def run_scan(
    *,
    path: str,
    source: str,
    warning_threshold: int,
    cov_cmd: str | None,
    lcov_path: str | None,
    reuse_coverage: bool,
    cwd: str,
) -> None:
    """Execute --scan: print site counts. Raises CoverageError on acquisition failure."""
    has_coverage = cov_cmd is not None or lcov_path is not None or reuse_coverage
    if has_coverage:
        lines, _ = scan_report_with_coverage(
            path,
            source,
            warning_threshold,
            cov_cmd=cov_cmd,
            lcov_path=lcov_path,
            reuse_coverage=reuse_coverage,
            cwd=cwd,
        )
    else:
        lines, _ = scan_report(path, source, warning_threshold)
    print("\n".join(lines))


def update_manifest(*, path: str, source: str) -> int:
    """Execute --update-manifest: embed or refresh manifest footer. Returns exit code."""
    existing, _ = extract_manifest(source)
    clean = strip_manifest(source)
    tested_at = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    candidate = build_manifest(clean, tested_at=tested_at)
    if existing is not None and manifests_structurally_equal(existing, candidate):
        print(f"Manifest unchanged: {path}")
        return 0
    embedded = embed_manifest(source, candidate)
    with open(path, "w") as f:
        f.write(embedded)
    print(f"Updated manifest: {path}")
    return 0


def check_manifest(*, path: str, source: str) -> int:
    """Check if the manifest embedded in source is up to date. Returns 0 if current, 1 if stale or missing."""
    clean = strip_manifest(source)
    existing, manifest_exists = extract_manifest(source)
    if not manifest_exists:
        print(f"Manifest missing: {path}")
        return 1
    tested_at = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    candidate = build_manifest(clean, tested_at=tested_at)
    if manifests_structurally_equal(existing, candidate):
        print(f"Manifest current: {path}")
        return 0
    print(f"Manifest stale: {path}")
    return 1


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

    n_selected = len(selected_sites)
    use_parallel = _should_run_parallel(max_workers, n_selected)

    _print_workers_header(max_workers, use_parallel, n_selected)

    baseline_duration, baseline_error = _run_baseline(test_command, source_dir)
    if baseline_error is not None:
        print(f"baseline failed: {baseline_error}")
        return 1

    with open(bak_path, "w") as f:
        f.write(clean_source)

    mutant_timeout = max(1.0, timeout_factor * baseline_duration)

    return _execute_mutations(
        selected_sites=selected_sites,
        clean_source=clean_source,
        path=path,
        source_dir=source_dir,
        cwd=cwd,
        test_command=test_command,
        mutant_timeout=mutant_timeout,
        max_workers=max_workers,
        use_parallel=use_parallel,
        tested_at=tested_at,
        bak_path=bak_path,
        uncovered_count=uncovered_count,
    )

# mutate4py-manifest-begin
# {"version":1,"tested_at":"2026-06-29T05:03:13Z","module_hash":"16f55e5c505832e494221ecf9b81cffe053f1e6ccbc289b87693ea7e5cb95d91","functions":[{"id":"func/_baseline_reason","name":"_baseline_reason","line":31,"end_line":35,"hash":"6037bd527abaf8a495048a7a504e32c167fda984b2204f6f777d58bb0bc94c61"},{"id":"func/_run_baseline","name":"_run_baseline","line":38,"end_line":45,"hash":"3df5ccb0f2bb2730f5c5c473dee47710112d9670db7df8685a33ec1bc87c3d6e"},{"id":"func/_filter_by_lines","name":"_filter_by_lines","line":48,"end_line":49,"hash":"1e7c8b1b8930f0fc810c32e6cf5844f1d0f054da3a90b748c972c9db0f5cad1e"},{"id":"func/_filter_by_fn","name":"_filter_by_fn","line":52,"end_line":53,"hash":"7bde9d2b50f085b8aec9909193a5391e7967834e9797b3cf6069210bee7df73c"},{"id":"func/_select_sites","name":"_select_sites","line":56,"end_line":69,"hash":"a4cfca336899bc823f71712ead79d24bbfd99f5e8a487d88aa1865b6b51bd3fa"},{"id":"func/_print_uncovered_block","name":"_print_uncovered_block","line":72,"end_line":82,"hash":"64af8f5bf37b3fd3381b6d81e93670387bd64de4c897712faeb864afd9321127"},{"id":"func/_restore_from_backup","name":"_restore_from_backup","line":85,"end_line":95,"hash":"eac2a96184bf954d27a9b87a70232574967423aa03fd629a886f30ca9ffa916b"},{"id":"func/_compute_manifest_diff","name":"_compute_manifest_diff","line":98,"end_line":109,"hash":"85d7a8153b82877267da65bc0ab725fb87385e45407d06309fc83bbbf1f7034f"},{"id":"func/_print_run_header","name":"_print_run_header","line":112,"end_line":131,"hash":"3ee0e5c23c4147496ab8628aaa1b000b53672e6ba77d49c36437086cf6e51e35"},{"id":"func/_run_mutation_loop","name":"_run_mutation_loop","line":134,"end_line":157,"hash":"62ecc231df504d04aa91002e7ebfe5ba6be4b65cc7401d3253138dff9ce06127"},{"id":"func/_on_parallel_result","name":"_on_parallel_result","line":160,"end_line":170,"hash":"4f1c7c1086c1cdebaf9fb79f281ac1fdf96dbd37b1ad5fd4a0eb98fa470ebc86"},{"id":"func/_run_parallel_workers","name":"_run_parallel_workers","line":173,"end_line":200,"hash":"9ab09719131630f5b62f83b4c5356373433737eec8f4420cd78df51491c02fca"},{"id":"func/_print_mutation_report","name":"_print_mutation_report","line":203,"end_line":220,"hash":"e276b7d9ac64ac7b88a5951026631f3cb9a986395dea5a722bc0f295f9c4f3fa"},{"id":"func/_print_workers_header","name":"_print_workers_header","line":223,"end_line":228,"hash":"9fb25897b2527f7eb8cd253159ee387c6943b7af27873c5cb5273b78355cd27e"},{"id":"func/_execute_mutations","name":"_execute_mutations","line":231,"end_line":267,"hash":"cc4c92dcd1be4fc3893401e1f9fdd7bae690208a1f081bb820be596c29948bd2"},{"id":"func/_acquire_covered_lines","name":"_acquire_covered_lines","line":270,"end_line":292,"hash":"3f39ffb7e5332f5ef3fdc2b652c7c1c2cd9aebbcee201a3fc9702b46e2e294d7"},{"id":"func/_is_effective_since_last_run","name":"_is_effective_since_last_run","line":295,"end_line":303,"hash":"789b9710423097f9bf44371ea3d22d3300a1c723c306f059244c06899436696f"},{"id":"func/_should_run_parallel","name":"_should_run_parallel","line":306,"end_line":307,"hash":"15249ea2817e81a958e42069ced55937242a9097ca031e88d4843613b8cf330d"},{"id":"func/_print_uncovered_if_needed","name":"_print_uncovered_if_needed","line":310,"end_line":317,"hash":"e7d50ad1b3b6feaa64ff9ca52d187451d70910e4bc8191261d27ba2c149cd1f6"},{"id":"func/_finalize_source","name":"_finalize_source","line":320,"end_line":327,"hash":"8b6724a1dbc4f3b9c217d2f49e562e8da4156c1f63c15095cf81f6ea10d9248a"},{"id":"func/scan_report","name":"scan_report","line":330,"end_line":347,"hash":"a93f4b1530dfba54505143b85e4c075297dd27837402a4767874bf43ddd9f1fe"},{"id":"func/scan_report_with_coverage","name":"scan_report_with_coverage","line":350,"end_line":383,"hash":"8faf41b91bf5c704478273f814bc91a8dcff880deb1fefd000b7a13f752eb2b4"},{"id":"func/run_scan","name":"run_scan","line":386,"end_line":410,"hash":"0656659f7878296231be9b065258fee175bc982a7c368c61c9b1d0162c910254"},{"id":"func/update_manifest","name":"update_manifest","line":413,"end_line":428,"hash":"468c784118b34a7ec9f90bc3fe9f32f1e750845dc830d5df137f4f1bfc4cb9b9"},{"id":"func/check_manifest","name":"check_manifest","line":431,"end_line":446,"hash":"cb8a9eb29e549309b9f041bedbe0df5f3150058256a736c91d66c6f4e41f4843"},{"id":"func/run_mutations","name":"run_mutations","line":449,"end_line":537,"hash":"d2ae2deb8e1c656c374d2e59a60a3c73a689d466ce0a446f41fc85cd26c3beaf"}]}
# mutate4py-manifest-end
