"""Mutation run loop — F4 core implementation + F6 parallel engine dispatch."""

import datetime
import os
import shlex
import subprocess
import sys
import time

from mutate4py._cmd import run_command as _run_command
from mutate4py._coverage import CoverageError, acquire_coverage

__all__ = [
    "CoverageError",
    "TestSelectionError",
    "check_manifest",
    "run_baseline",
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
    parse_sidecar_manifest,
    reconcile_manifest,
    serialize_sidecar_manifest,
    source_sha256,
    strip_manifest,
)


def _baseline_reason(result: subprocess.CompletedProcess) -> str:
    stderr = (result.stderr or b"").decode(errors="replace").strip()
    if stderr:
        return stderr.splitlines()[0]
    return f"exit code {result.returncode}"


def run_baseline(cmd: str, cwd: str) -> tuple[float, str | None]:
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


def _sidecar_path(source_path: str) -> str:
    """Return the sidecar manifest path for a source file: <source_path>.manifest.json."""
    return source_path + ".manifest.json"


def read_sidecar_manifest(source_path: str) -> tuple[dict | None, bool]:
    """Read source_path's manifest from its own sidecar JSON file.

    Missing sidecar, parse failure, or valid-but-non-dict JSON => (None, False),
    never an error (mirrors extract_manifest).
    """
    sidecar_path = _sidecar_path(source_path)
    if not os.path.isfile(sidecar_path):
        return None, False
    with open(sidecar_path) as f:
        text = f.read()
    parsed, ok = parse_sidecar_manifest(text)
    return (parsed, True) if ok and isinstance(parsed, dict) else (None, False)


def write_sidecar_manifest(source_path: str, manifest: dict) -> None:
    """Write source_path's manifest to its own sidecar JSON file."""
    with open(_sidecar_path(source_path), "w") as f:
        f.write(serialize_sidecar_manifest(manifest))


def _read_existing_manifest(
    source: str, manifest_file: bool, path: str
) -> tuple[dict | None, bool]:
    """Read the prior manifest from its configured storage (sidecar or in-source footer)."""
    if manifest_file:
        return read_sidecar_manifest(path)
    return extract_manifest(source)


def _compute_manifest_diff(
    source: str,
    path: str,
    manifest_file: bool = False,
) -> tuple[str, dict | None, bool, set[str], str]:
    """Strip manifest, discover sites, diff; return (clean_source, existing_manifest, manifest_exists, changed_fn_ids, tested_at)."""
    clean_source = strip_manifest(source)
    existing_manifest, manifest_exists = _read_existing_manifest(
        source, manifest_file, path
    )
    tested_at = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    current_manifest = build_manifest(clean_source, tested_at=tested_at)
    changed_fn_ids = diff_manifests(existing_manifest, current_manifest)
    return clean_source, existing_manifest, manifest_exists, changed_fn_ids, tested_at


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


class TestSelectionError(Exception):
    """A selected site the test-context db cannot account for (case 3)."""


# The selected sites are LCOV-covered by construction, so a miss is always an
# input defect, never uncovered code — hence a hard error rather than a fallback.
_DISAGREEMENT_HINTS = {
    "line-absent": "line is LCOV-covered but absent from the test-context db "
    "(stale db: regenerate it with pytest --cov-context=test)",
    "file-absent": "file is not in the test-context db at all "
    "(path-format mismatch, or its coverage was recorded in a subprocess)",
}


def _build_mutant_command(
    test_command: str, test_ctx_db, abs_source_path: str, site: Site
) -> tuple[str, str | None]:
    """Return (command, selection) for site; selection is None without a context db.

    "narrowed" runs only the tests covering site.line; "static" runs the full
    test_command because the line executes at import time and no test owns it.
    """
    if test_ctx_db is None:
        return test_command, None
    outcome, node_ids = test_ctx_db.tests_for_line(abs_source_path, site.line)
    if outcome == "narrowed":
        return (
            f"{test_command} {' '.join(shlex.quote(n) for n in node_ids)}",
            "narrowed",
        )
    if outcome == "static":
        return test_command, "static"
    # Every other outcome raises, so an unrecognized one can never fall through to
    # a full-suite run that the report would then miscount as narrowed.
    hint = _DISAGREEMENT_HINTS.get(
        outcome, f"unrecognized selection outcome {outcome!r}"
    )
    raise TestSelectionError(f"{abs_source_path}:{site.line}: {hint}")


def _run_single_mutant(fork_server, cmd: str, cwd: str, mutant_timeout: float) -> str:
    """Execute one already-spliced mutant; return its status.

    Routes through the primed fork server when given, else the existing
    per-mutant subprocess model.
    """
    if fork_server is not None:
        status, _ = fork_server.run(mutant_timeout)
    else:
        status, _ = _run_command(cmd, cwd, mutant_timeout)
    return status


def _run_mutation_loop(
    selected_sites: list[Site],
    clean_source: str,
    path: str,
    cwd: str,
    test_command: str,
    mutant_timeout: float,
    test_ctx_db=None,
    abs_source_path: str = "",
    fork_server=None,
) -> tuple[dict, list[Site], dict[str, int] | None]:
    """Run each selected site; the third return is the narrowed/static tally, or
    None when no context db is in play. Raises TestSelectionError on a
    selection disagreement.

    fork_server, when given (a primed mutate4py._fork_server.ForkServer),
    replaces the per-mutant subprocess with a fork() of the already-warm
    pytest process instead. It is only ever passed alongside test_ctx_db=None
    (--fork-server and --test-contexts are mutually exclusive at the CLI),
    so _build_mutant_command is still cheap and side-effect-free to call
    unconditionally: with no context db it just returns (test_command, None).
    """
    total_selected = len(selected_sites)
    counts: dict[str, int] = {"killed": 0, "timeout": 0, "survived": 0}
    selection_counts: dict[str, int] = {"narrowed": 0, "static": 0}
    survivors: list[Site] = []
    for i, site in enumerate(selected_sites, 1):
        # Built before the splice so a disagreement aborts with the source untouched.
        cmd, selection = _build_mutant_command(
            test_command, test_ctx_db, abs_source_path, site
        )
        if selection is not None:
            selection_counts[selection] += 1
        mutated = apply_mutant(clean_source, site)
        with open(path, "w") as f:
            f.write(mutated)
        status = _run_single_mutant(fork_server, cmd, cwd, mutant_timeout)
        counts[status] += 1
        if status == "survived":
            survivors.append(site)
        fid_suffix = f": {site.function_id}" if site.function_id else ""
        print(
            f"[{i}/{total_selected}] {status} line {site.line} {site.desc}{fid_suffix}"
        )
    return counts, survivors, (selection_counts if test_ctx_db is not None else None)


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
    selection_counts: dict[str, int] | None = None,
) -> None:
    killed_total = counts["killed"] + counts["timeout"]
    print()
    print("Mutation Report")
    print("===============")
    print(f"Killed: {killed_total}")
    print(f"Survived: {counts['survived']}")
    print(f"Uncovered: {uncovered_count}")
    if selection_counts is not None:
        print(
            f"Test selection: narrowed {selection_counts['narrowed']}, "
            f"static {selection_counts['static']}"
        )
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
    cwd: str,
    test_command: str,
    mutant_timeout: float,
    max_workers: int,
    use_parallel: bool,
    tested_at: str,
    bak_path: str,
    uncovered_count: int,
    existing_manifest: dict | None = None,
    test_ctx_db=None,
    abs_source_path: str = "",
    manifest_file: bool = False,
    fork_server=None,
) -> int:
    """Run serial or parallel mutations, finalize source, print report. Returns exit code.

    A TestSelectionError from the serial loop propagates to run_mutations, after
    the source has been finalized exactly as a completed run would leave it.
    """
    error_msg = None
    selection_counts = None
    try:
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
        else:
            counts, survivors, selection_counts = _run_mutation_loop(
                selected_sites,
                clean_source,
                path,
                cwd,
                test_command,
                mutant_timeout,
                test_ctx_db=test_ctx_db,
                abs_source_path=abs_source_path,
                fork_server=fork_server,
            )
    finally:
        _finalize_source(
            path,
            clean_source,
            tested_at,
            bak_path,
            manifest_file,
            existing_manifest=existing_manifest,
        )
    if error_msg is not None:
        print(error_msg)
        return 1
    _print_mutation_report(counts, survivors, uncovered_count, selection_counts)
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


def _write_manifest_output(
    path: str,
    clean_source: str,
    manifest: dict,
    manifest_file: bool,
    *,
    write_source: bool = True,
    write_manifest: bool = True,
) -> None:
    """Write clean_source/manifest to their configured storage (sidecar or in-source footer).

    In embed mode (manifest_file is False) source and footer are always written
    together as one file, so write_source/write_manifest are ignored there.
    """
    if manifest_file:
        if write_source:
            with open(path, "w") as f:
                f.write(clean_source)
        if write_manifest:
            write_sidecar_manifest(path, manifest)
    else:
        with open(path, "w") as f:
            f.write(embed_manifest(clean_source, manifest))


def _finalize_source(
    path: str,
    clean_source: str,
    tested_at: str,
    bak_path: str,
    manifest_file: bool = False,
    *,
    existing_manifest: dict | None = None,
) -> None:
    # Unlike update_manifest, the write can't be skipped outright: a run with
    # selected sites leaves the last-tested mutant on disk (the per-site loop
    # never reverts), so clean_source must always be restored. Only the
    # manifest choice is conditional — reusing existing_manifest keeps the
    # written bytes identical to what's already on disk when nothing changed.
    candidate_manifest = build_manifest(clean_source, tested_at=tested_at)
    manifest_to_embed = reconcile_manifest(existing_manifest, candidate_manifest)
    _write_manifest_output(path, clean_source, manifest_to_embed, manifest_file)
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


def update_manifest(*, path: str, source: str, manifest_file: bool = False) -> int:
    """Execute --update-manifest: refresh the manifest in its configured storage. Returns exit code."""
    existing, _ = _read_existing_manifest(source, manifest_file, path)
    clean = strip_manifest(source)
    tested_at = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    candidate = build_manifest(clean, tested_at=tested_at)
    manifest_to_embed = reconcile_manifest(existing, candidate)
    manifest_changed = manifest_to_embed is not existing

    if manifest_file:
        source_has_stale_footer = clean != source
        if not manifest_changed and not source_has_stale_footer:
            print(f"Manifest unchanged: {path}")
            return 0
        _write_manifest_output(
            path,
            clean,
            manifest_to_embed,
            manifest_file,
            write_source=source_has_stale_footer,
            write_manifest=manifest_changed,
        )
        print(f"Updated manifest: {path}")
        return 0

    if not manifest_changed:
        print(f"Manifest unchanged: {path}")
        return 0
    _write_manifest_output(path, clean, manifest_to_embed, manifest_file)
    print(f"Updated manifest: {path}")
    return 0


def check_manifest(*, path: str, source: str, manifest_file: bool = False) -> int:
    """Check if the manifest in its configured storage is up to date. Returns 0 if current, 1 if stale or missing."""
    clean = strip_manifest(source)
    existing, manifest_exists = _read_existing_manifest(source, manifest_file, path)
    if not manifest_exists:
        print(f"Manifest missing: {path}")
        return 1
    existing_source_sha256 = existing.get("source_sha256")
    if existing_source_sha256 is not None and existing_source_sha256 == source_sha256(
        clean
    ):
        print(f"Manifest current: {path}")
        return 0
    tested_at = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    candidate = build_manifest(clean, tested_at=tested_at)
    if manifests_structurally_equal(existing, candidate):
        print(f"Manifest current: {path}")
        return 0
    print(f"Manifest stale: {path}")
    return 1


def _setup_test_context_db(test_contexts_path: str | None, max_workers: int):
    """Open the test-context db if requested; force serial execution when doing so.

    Returns (test_ctx_db_or_None, effective_max_workers).
    """
    if test_contexts_path is None:
        return None, max_workers
    from mutate4py._test_selection import TestContextDB

    test_ctx_db = TestContextDB(test_contexts_path)
    effective_max_workers = 0 if max_workers >= 2 else max_workers
    return test_ctx_db, effective_max_workers


def _prepare_fork_server(
    requested: bool, test_command: str, cwd: str, guarded_path: str
):
    """Build and prime a ForkServer for the serial loop, or None to keep the
    existing per-mutant subprocess model.

    Never raises: any unavailability or priming failure (wrong platform,
    test_command isn't a plain `pytest` invocation, pytest not importable in
    this process, or the target leaking into sys.modules during priming) is
    reported and treated as "fall back", never as a hard error — the fork
    server is a best-effort accelerator, on by default, not a
    correctness-affecting choice, so it degrades silently to the slower but
    always-correct subprocess model wherever it isn't safe or applicable.
    """
    if not requested:
        return None
    from mutate4py._fork_server import ForkServer, ForkServerUnavailable, is_available

    if not is_available(test_command):
        print(
            "note: fork-server fast path needs a plain `pytest` --test-command "
            "on a POSIX platform; using the per-mutant subprocess model instead."
        )
        return None
    extra_args = shlex.split(test_command)[1:]
    server = ForkServer(cwd=cwd, extra_args=extra_args, guarded_path=guarded_path)
    try:
        server.prime()
    except ForkServerUnavailable as exc:
        print(
            f"note: fork-server fast path unavailable ({exc}); "
            "using the per-mutant subprocess model instead."
        )
        return None
    return server


def _fork_server_eligible(
    fork_server_requested: bool,
    use_parallel: bool,
    test_ctx_db,
    selected_sites: list,
) -> bool:
    """Whether the fork-server fast path may be attempted for this run.

    Mutually exclusive with parallel workers and per-mutant test-context
    narrowing: ForkServer.run always executes the full test_command with no
    per-site command variation, so it cannot honor either.
    """
    return (
        fork_server_requested
        and not use_parallel
        and test_ctx_db is None
        and bool(selected_sites)
    )


def _load_clean_source(
    path: str, bak_path: str, source: str, manifest_file: bool = False
) -> tuple[str, dict | None, bool, set[str], str, list[Site], int]:
    """Rescue from backup if needed, strip/diff the manifest, and discover sites.

    Returns (clean_source, existing_manifest, manifest_exists, changed_fn_ids, tested_at, all_sites, changed_count).
    """
    rescued = _restore_from_backup(path, bak_path)
    if rescued is not None:
        source = rescued
    (
        clean_source,
        existing_manifest,
        manifest_exists,
        changed_fn_ids,
        tested_at,
    ) = _compute_manifest_diff(source, path, manifest_file)
    all_sites = discover_sites(clean_source)
    changed_count = len([s for s in all_sites if s.function_id in changed_fn_ids])
    return (
        clean_source,
        existing_manifest,
        manifest_exists,
        changed_fn_ids,
        tested_at,
        all_sites,
        changed_count,
    )


def _resolve_baseline_duration(
    baseline_duration: float | None, test_command: str, cwd: str
) -> tuple[float | None, str | None]:
    """Return (duration, error). A pre-supplied duration is passed through untouched."""
    if baseline_duration is not None:
        return baseline_duration, None
    return run_baseline(test_command, cwd)


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
    min_timeout: float = 1.0,
    cwd: str,
    baseline_duration: float | None = None,
    test_contexts_path: str | None = None,
    manifest_file: bool = False,
    fork_server_requested: bool = True,
) -> int:
    """Execute the mutation run loop.

    Returns 0, 1 (coverage/baseline failure), or 2 (the test-context db and the
    LCOV coverage disagree about a selected site).
    """
    source_dir = os.path.dirname(os.path.abspath(path))
    bak_path = os.path.join(source_dir, os.path.basename(path) + ".bak")

    test_ctx_db, max_workers = _setup_test_context_db(test_contexts_path, max_workers)
    try:
        (
            clean_source,
            existing_manifest,
            manifest_exists,
            changed_fn_ids,
            tested_at,
            all_sites,
            changed_count,
        ) = _load_clean_source(path, bak_path, source, manifest_file)

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
            all_sites,
            covered_lines,
            changed_fn_ids,
            effective_since_last_run,
            lines_filter,
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

        baseline_duration, baseline_error = _resolve_baseline_duration(
            baseline_duration, test_command, cwd
        )
        if baseline_error is not None:
            print(f"baseline failed: {baseline_error}")
            return 1

        with open(bak_path, "w") as f:
            f.write(clean_source)

        mutant_timeout = max(min_timeout, timeout_factor * baseline_duration)

        fork_server = _prepare_fork_server(
            _fork_server_eligible(
                fork_server_requested, use_parallel, test_ctx_db, selected_sites
            ),
            test_command,
            cwd,
            os.path.abspath(path),
        )

        return _execute_mutations(
            selected_sites=selected_sites,
            clean_source=clean_source,
            path=path,
            cwd=cwd,
            test_command=test_command,
            mutant_timeout=mutant_timeout,
            max_workers=max_workers,
            use_parallel=use_parallel,
            tested_at=tested_at,
            bak_path=bak_path,
            uncovered_count=uncovered_count,
            existing_manifest=existing_manifest,
            test_ctx_db=test_ctx_db,
            abs_source_path=os.path.abspath(path),
            manifest_file=manifest_file,
            fork_server=fork_server,
        )
    except TestSelectionError as exc:
        print(
            f"error: test-context db disagrees with coverage: {exc}",
            file=sys.stderr,
        )
        return 2
    finally:
        if test_ctx_db is not None:
            test_ctx_db.close()


# mutate4py-manifest-begin
# {"version":1,"tested_at":"2026-08-09T05:07:28Z","module_hash":"37b63f8cd695d4b38846ea284ec9d0b6725797c2494752ee806f047bd347e35d","source_sha256":"1d77cc3fca5b394c9ddef20f4f31e8bdd02581eaeb02118fa385f74d9a03c043","functions":[{"id":"func/_baseline_reason","name":"_baseline_reason","line":39,"end_line":43,"hash":"6037bd527abaf8a495048a7a504e32c167fda984b2204f6f777d58bb0bc94c61"},{"id":"func/run_baseline","name":"run_baseline","line":46,"end_line":53,"hash":"9c1ef7c2bd0a7a952d9f0e60242e19d1381e4ae12d5fc8d2bfac56334392ebff"},{"id":"func/_filter_by_lines","name":"_filter_by_lines","line":56,"end_line":57,"hash":"1e7c8b1b8930f0fc810c32e6cf5844f1d0f054da3a90b748c972c9db0f5cad1e"},{"id":"func/_filter_by_fn","name":"_filter_by_fn","line":60,"end_line":61,"hash":"7bde9d2b50f085b8aec9909193a5391e7967834e9797b3cf6069210bee7df73c"},{"id":"func/_select_sites","name":"_select_sites","line":64,"end_line":77,"hash":"a4cfca336899bc823f71712ead79d24bbfd99f5e8a487d88aa1865b6b51bd3fa"},{"id":"func/_print_uncovered_block","name":"_print_uncovered_block","line":80,"end_line":90,"hash":"64af8f5bf37b3fd3381b6d81e93670387bd64de4c897712faeb864afd9321127"},{"id":"func/_restore_from_backup","name":"_restore_from_backup","line":93,"end_line":103,"hash":"eac2a96184bf954d27a9b87a70232574967423aa03fd629a886f30ca9ffa916b"},{"id":"func/_sidecar_path","name":"_sidecar_path","line":106,"end_line":108,"hash":"af8f8cfc5561f9534e283daa8fd83073dbdf8b269beef3956138b50c81197dfd"},{"id":"func/read_sidecar_manifest","name":"read_sidecar_manifest","line":111,"end_line":123,"hash":"3bdb1511b8b328a09f3379df51d4c0379af5cf6ed1b9e52f087c65a7a061113e"},{"id":"func/write_sidecar_manifest","name":"write_sidecar_manifest","line":126,"end_line":129,"hash":"a1286abc647074d89e0b13b323d1bab95d8ff1268d8a116f1f8aea6a747d775f"},{"id":"func/_read_existing_manifest","name":"_read_existing_manifest","line":132,"end_line":138,"hash":"2725f1e89c2b925f5d846d2739b0a71d40c9dece1fcf2f96718de6c42d1466be"},{"id":"func/_compute_manifest_diff","name":"_compute_manifest_diff","line":141,"end_line":156,"hash":"5bf0f5702fcc2258e490b90ee0a86d53bcd0a6b3b08334fa8ba9818cca2a3fae"},{"id":"func/_print_run_header","name":"_print_run_header","line":159,"end_line":178,"hash":"3ee0e5c23c4147496ab8628aaa1b000b53672e6ba77d49c36437086cf6e51e35"},{"id":"func/_build_mutant_command","name":"_build_mutant_command","line":195,"end_line":218,"hash":"9dadd97a7e9c7e001d6f773b1776379e86106c9221180797357242d440745237"},{"id":"func/_run_single_mutant","name":"_run_single_mutant","line":221,"end_line":231,"hash":"69aa6636055bdba948183b5541fd63e214b0a3fa5dfb67550049fac524608d54"},{"id":"func/_run_mutation_loop","name":"_run_mutation_loop","line":234,"end_line":278,"hash":"115ad5e89b8a6b604f7de724dfb34f2764b3181542e9c82b534d28596283c618"},{"id":"func/_on_parallel_result","name":"_on_parallel_result","line":281,"end_line":291,"hash":"4f1c7c1086c1cdebaf9fb79f281ac1fdf96dbd37b1ad5fd4a0eb98fa470ebc86"},{"id":"func/_run_parallel_workers","name":"_run_parallel_workers","line":294,"end_line":321,"hash":"9ab09719131630f5b62f83b4c5356373433737eec8f4420cd78df51491c02fca"},{"id":"func/_print_mutation_report","name":"_print_mutation_report","line":324,"end_line":347,"hash":"8fbac40a95965db2b883bdf80eb68252eb87579025a420de46697cc2d7466ce0"},{"id":"func/_print_workers_header","name":"_print_workers_header","line":350,"end_line":355,"hash":"9fb25897b2527f7eb8cd253159ee387c6943b7af27873c5cb5273b78355cd27e"},{"id":"func/_execute_mutations","name":"_execute_mutations","line":358,"end_line":420,"hash":"4a013df19aab2ca7d9599d068909a21b97ec2508f56070ad7334b7bb648fdcbe"},{"id":"func/_acquire_covered_lines","name":"_acquire_covered_lines","line":423,"end_line":445,"hash":"3f39ffb7e5332f5ef3fdc2b652c7c1c2cd9aebbcee201a3fc9702b46e2e294d7"},{"id":"func/_is_effective_since_last_run","name":"_is_effective_since_last_run","line":448,"end_line":456,"hash":"789b9710423097f9bf44371ea3d22d3300a1c723c306f059244c06899436696f"},{"id":"func/_should_run_parallel","name":"_should_run_parallel","line":459,"end_line":460,"hash":"15249ea2817e81a958e42069ced55937242a9097ca031e88d4843613b8cf330d"},{"id":"func/_print_uncovered_if_needed","name":"_print_uncovered_if_needed","line":463,"end_line":470,"hash":"e7d50ad1b3b6feaa64ff9ca52d187451d70910e4bc8191261d27ba2c149cd1f6"},{"id":"func/_write_manifest_output","name":"_write_manifest_output","line":473,"end_line":495,"hash":"95e0db56c3aefbbba68d167d6bfffc5f78e3f0b6b01bcb88616a5005d7fea48c"},{"id":"func/_finalize_source","name":"_finalize_source","line":498,"end_line":516,"hash":"5544df0b5c7eb0900c061dcc9514d4b301564eb7cb0f6b27bed9f05956ddad67"},{"id":"func/scan_report","name":"scan_report","line":519,"end_line":536,"hash":"a93f4b1530dfba54505143b85e4c075297dd27837402a4767874bf43ddd9f1fe"},{"id":"func/scan_report_with_coverage","name":"scan_report_with_coverage","line":539,"end_line":572,"hash":"8faf41b91bf5c704478273f814bc91a8dcff880deb1fefd000b7a13f752eb2b4"},{"id":"func/run_scan","name":"run_scan","line":575,"end_line":599,"hash":"0656659f7878296231be9b065258fee175bc982a7c368c61c9b1d0162c910254"},{"id":"func/update_manifest","name":"update_manifest","line":602,"end_line":634,"hash":"9f2c9e6992fbe51264382aa5b86211c4b5b9994e610022522baf647f9d4b811d"},{"id":"func/check_manifest","name":"check_manifest","line":637,"end_line":658,"hash":"c63c000c71d65f1e0dbff29dbf19afc29ea4ba80f155bfa3ccd6439573782812"},{"id":"func/_setup_test_context_db","name":"_setup_test_context_db","line":661,"end_line":672,"hash":"c1eed2316ef608c58b742dca1ff2394c3b15856b4f48788fdf17da0f6f60b8d8"},{"id":"func/_prepare_fork_server","name":"_prepare_fork_server","line":675,"end_line":709,"hash":"b9162b3c2e05e7c209d5a8667530ec6922810e9cc0cf85a99b54b4ec80cedcd8"},{"id":"func/_fork_server_eligible","name":"_fork_server_eligible","line":712,"end_line":729,"hash":"5472e60f0bfb427e246693ca354636cd22af7731105662cdd8e50d3cd9cc539e"},{"id":"func/_load_clean_source","name":"_load_clean_source","line":732,"end_line":759,"hash":"cd6b9f5396b889f182edab35188e167512b5d360dd8fb310f7e6c4c072cb30dc"},{"id":"func/_resolve_baseline_duration","name":"_resolve_baseline_duration","line":762,"end_line":768,"hash":"9885e555d18e824057b581e30b0d2345e78e9444ef82f6d5289d11977a6dd1c8"},{"id":"func/run_mutations","name":"run_mutations","line":771,"end_line":898,"hash":"4468dfc6bbb9ae7bf45f9ac5394ca89c60537d42ad4f540be22e7d8bcb39babe"}]}
# mutate4py-manifest-end
