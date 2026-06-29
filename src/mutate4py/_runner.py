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
# {"version":1,"tested_at":"2026-06-29T00:53:58Z","module_hash":"e8a5554255719f38a8849cd077903fa929f67dbeca98efb7269beac342f4f84e","functions":[{"id":"func/_baseline_reason","name":"_baseline_reason","line":31,"end_line":35,"hash":"8077d79ea9563e334267d0660aa610533243eb443308a184e074e9ba364157b1"},{"id":"func/_run_baseline","name":"_run_baseline","line":38,"end_line":45,"hash":"4a0db3e4bac161c3c57659179b915fcb7c91d1ed6d0778fd793fd51a9623141e"},{"id":"func/_filter_by_lines","name":"_filter_by_lines","line":48,"end_line":49,"hash":"2a4ed9bd9d8bdc0873c2321b68f16c922c6b410532b7951eb992c365ae107a04"},{"id":"func/_filter_by_fn","name":"_filter_by_fn","line":52,"end_line":53,"hash":"f269bc21c93c524d6806f52eeeba43497208dd64ca95eedd28c79def73c6beb9"},{"id":"func/_select_sites","name":"_select_sites","line":56,"end_line":69,"hash":"3586ab845fb3d23e318937905e506646c995517e4a37813e0694f64d5ab37e87"},{"id":"func/_print_uncovered_block","name":"_print_uncovered_block","line":72,"end_line":82,"hash":"14dc2593bb8e02d284163a264464f6762b2fbd1cb733d78a28c80ed3928ddc7a"},{"id":"func/_restore_from_backup","name":"_restore_from_backup","line":85,"end_line":95,"hash":"b799d47401a754d12c14a2c0d852a994e77df969523715e1348ff0082fcb60a0"},{"id":"func/_compute_manifest_diff","name":"_compute_manifest_diff","line":98,"end_line":109,"hash":"598ada2a90d8ed306190da27a225d6676b113bab929abbc64d7a1d3488bbebff"},{"id":"func/_print_run_header","name":"_print_run_header","line":112,"end_line":131,"hash":"56364f0bdced9fe617480df00a39de77ae0d851d95c3d306d18908daae0b8eef"},{"id":"func/_run_mutation_loop","name":"_run_mutation_loop","line":134,"end_line":157,"hash":"96e2e58af65e93b05cec3f84f74ef77bbaf9df5758faae0c67cbdb38ad2dadd8"},{"id":"func/_on_parallel_result","name":"_on_parallel_result","line":160,"end_line":170,"hash":"e87dde88be2ca79bcfeae7fa1f0dcbbe2504bb12a4a2483703942edac44db5c3"},{"id":"func/_run_parallel_workers","name":"_run_parallel_workers","line":173,"end_line":200,"hash":"df3ae1d76563149136c7e798a5835968ed4d4c2ffb4da00713fd87ae5a0c93ee"},{"id":"func/_print_mutation_report","name":"_print_mutation_report","line":203,"end_line":220,"hash":"29e542fcad6ea6b5283037e36d6d7306d532627f56466780753390530b864c58"},{"id":"func/_print_workers_header","name":"_print_workers_header","line":223,"end_line":228,"hash":"2207ff9275ed8f93672e662ed33fbbd43414921fb6596c9a9b8a4cae4fd57b1f"},{"id":"func/_execute_mutations","name":"_execute_mutations","line":231,"end_line":267,"hash":"fecf85755dda1aed848f394cd0e7c0bf3b372204aabdcfef8cc311af5b7fbeda"},{"id":"func/_acquire_covered_lines","name":"_acquire_covered_lines","line":270,"end_line":292,"hash":"365e0702a640a4e753bdf3367ed8859d48a42b1385deb9fee1bda0d8b4836115"},{"id":"func/_is_effective_since_last_run","name":"_is_effective_since_last_run","line":295,"end_line":303,"hash":"f09775d417a7ff141ae8e4bc2122221c75fce7f3c59613e9b9c18b747b127d24"},{"id":"func/_should_run_parallel","name":"_should_run_parallel","line":306,"end_line":307,"hash":"7f4c318a45bbe71d844f2cfb51a828f3182f1593b98ae945a318e70586784035"},{"id":"func/_print_uncovered_if_needed","name":"_print_uncovered_if_needed","line":310,"end_line":317,"hash":"2b221863e53ac25c57295355e6df2f43fb4088bd212aa2844b3769e4b5af5c95"},{"id":"func/_finalize_source","name":"_finalize_source","line":320,"end_line":327,"hash":"3a74402750c7108257cd13f1a290df9c30bacb0a03d7f58c10ab48fd667b249e"},{"id":"func/scan_report","name":"scan_report","line":330,"end_line":347,"hash":"c371124bd39eb3a5d579a77af322f61b2ed73d15dee24a91565e4df41029b065"},{"id":"func/scan_report_with_coverage","name":"scan_report_with_coverage","line":350,"end_line":383,"hash":"b495db85fb37ccff108305a0e92a9a0d8065fa115a70a52278b6265271261b86"},{"id":"func/run_scan","name":"run_scan","line":386,"end_line":410,"hash":"2b491eacb97dd968bed80a724ace736a9ce53cfda784abf349bb20d1dd4f3b3f"},{"id":"func/update_manifest","name":"update_manifest","line":413,"end_line":428,"hash":"a4221d9f85fdf92cc490f64a4cecf06920947187310cc8195c5f06b7df2c46b1"},{"id":"func/check_manifest","name":"check_manifest","line":431,"end_line":446,"hash":"fb28a7f8ef449a89759be9bc78a286d14b8eb20c084cd302bec39255e67f66a7"},{"id":"func/run_mutations","name":"run_mutations","line":449,"end_line":537,"hash":"95a8ae064206214020dcd8db41b6887a42c04624738a4524b92d11b0917f6ce4"}]}
# mutate4py-manifest-end
