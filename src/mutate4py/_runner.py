"""Mutation run loop — F4 core implementation + F6 parallel engine dispatch."""

import dataclasses
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
    "CoverageSource",
    "RunMutationsRequest",
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


@dataclasses.dataclass(frozen=True)
class ManifestLocation:
    """Where a source file's manifest lives: sidecar JSON alongside it, or an embedded footer."""

    path: str
    manifest_file: bool = False


@dataclasses.dataclass
class MutantExecCtx:
    """Where and how mutants are executed for one run: paths, command, timeout, and dispatch mode."""

    path: str
    cwd: str
    test_command: str
    mutant_timeout: float
    max_workers: int = 0
    use_parallel: bool = False
    abs_source_path: str = ""
    test_ctx_db: object = None
    fork_server: object = None


@dataclasses.dataclass
class FinalizeInputs:
    """What _finalize_source needs to write the manifest back after a run."""

    tested_at: str
    bak_path: str
    loc: ManifestLocation
    existing_manifest: dict | None = None


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
    test_command: str
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
    fork_server_requested: bool = True


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
    *,
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


def _print_lines(lines: list[str]) -> None:
    """Print a report block's lines as one call, or nothing when the block is empty."""
    if lines:
        print("\n".join(lines))


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


def _read_existing_manifest(source: str, loc: ManifestLocation) -> tuple[dict | None, bool]:
    """Read the prior manifest from its configured storage (sidecar or in-source footer)."""
    if loc.manifest_file:
        return read_sidecar_manifest(loc.path)
    return extract_manifest(source)


def _compute_manifest_diff(source: str, loc: ManifestLocation) -> tuple[str, dict | None, bool, set[str], str]:
    """Strip manifest, discover sites, diff.

    Returns (clean_source, existing_manifest, manifest_exists, changed_fn_ids, tested_at).
    """
    clean_source = strip_manifest(source)
    existing_manifest, manifest_exists = _read_existing_manifest(source, loc)
    tested_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    current_manifest = build_manifest(clean_source, tested_at=tested_at)
    changed_fn_ids = diff_manifests(existing_manifest, current_manifest)
    return clean_source, existing_manifest, manifest_exists, changed_fn_ids, tested_at


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


def _build_mutant_command(test_command: str, test_ctx_db, abs_source_path: str, site: Site) -> tuple[str, str | None]:
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
    hint = _DISAGREEMENT_HINTS.get(outcome, f"unrecognized selection outcome {outcome!r}")
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


def _serial_progress_line(i: int, total_selected: int, status: str, site: Site) -> str:
    fid_suffix = f": {site.function_id}" if site.function_id else ""
    return f"[{i}/{total_selected}] {status} line {site.line} {site.desc}{fid_suffix}"


def _run_mutation_loop(
    selected_sites: list[Site],
    clean_source: str,
    ctx: MutantExecCtx,
) -> tuple[dict, list[Site], dict[str, int] | None]:
    """Run each selected site; the third return is the narrowed/static tally, or
    None when no context db is in play. Raises TestSelectionError on a
    selection disagreement.

    ctx.fork_server, when given (a primed mutate4py._fork_server.ForkServer),
    replaces the per-mutant subprocess with a fork() of the already-warm
    pytest process instead. It is only ever set alongside ctx.test_ctx_db=None
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
        cmd, selection = _build_mutant_command(ctx.test_command, ctx.test_ctx_db, ctx.abs_source_path, site)
        if selection is not None:
            selection_counts[selection] += 1
        mutated = apply_mutant(clean_source, site)
        with open(ctx.path, "w") as f:
            f.write(mutated)
        status = _run_single_mutant(ctx.fork_server, cmd, ctx.cwd, ctx.mutant_timeout)
        counts[status] += 1
        if status == "survived":
            survivors.append(site)
        print(_serial_progress_line(i, total_selected, status, site))
    return counts, survivors, (selection_counts if ctx.test_ctx_db is not None else None)


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


def _run_parallel_workers(
    selected_sites: list[Site],
    clean_source: str,
    ctx: MutantExecCtx,
) -> tuple[dict | None, list[Site] | None, str | None]:
    """Dispatch the parallel engine; return (counts, survivors, error_msg)."""
    from mutate4py._workers import ParallelRunError, ParallelRunRequest, WorkerFailureError, run_parallel

    try:
        counts, survivors = run_parallel(
            ParallelRunRequest(
                selected_sites=selected_sites,
                clean_source=clean_source,
                source_path=ctx.path,
                cwd=ctx.cwd,
                test_command=ctx.test_command,
                mutant_timeout=ctx.mutant_timeout,
                max_workers=ctx.max_workers,
                on_result=_on_parallel_result,
            )
        )
        return counts, survivors, None
    except WorkerFailureError as e:
        return None, None, f"mutation worker failed: {e}"
    except ParallelRunError as e:
        return None, None, str(e)


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


def _execute_mutations(
    *,
    selected_sites: list[Site],
    clean_source: str,
    ctx: MutantExecCtx,
    uncovered_count: int,
    finalize: FinalizeInputs,
) -> int:
    """Run serial or parallel mutations, finalize source, print report. Returns exit code.

    A TestSelectionError from the serial loop propagates to run_mutations, after
    the source has been finalized exactly as a completed run would leave it.
    """
    error_msg = None
    selection_counts = None
    try:
        if ctx.use_parallel:
            counts, survivors, error_msg = _run_parallel_workers(selected_sites, clean_source, ctx)
        else:
            counts, survivors, selection_counts = _run_mutation_loop(selected_sites, clean_source, ctx)
    finally:
        _finalize_source(
            clean_source,
            finalize.tested_at,
            finalize.bak_path,
            finalize.loc,
            existing_manifest=finalize.existing_manifest,
        )
    if error_msg is not None:
        print(error_msg)
        return 1
    _print_lines(_mutation_report_lines(counts, survivors, uncovered_count, selection_counts))
    return 0


def _acquire_covered_lines(
    cov_cmd: str | None,
    lcov_path: str | None,
    *,
    reuse_coverage: bool,
    cwd: str,
    abs_source: str,
) -> tuple[set[int] | None, str | None]:
    """Acquire coverage; return (covered_lines, error_message_or_None)."""
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
        return covered_lines, None
    except CoverageError as exc:
        return None, str(exc)


def _is_effective_since_last_run(
    *,
    since_last_run: bool,
    manifest_exists: bool,
    mutate_all: bool,
    lines_filter: set[int] | None,
) -> bool:
    return since_last_run or (manifest_exists and not mutate_all and lines_filter is None)


def _should_run_parallel(max_workers: int, n_selected: int) -> bool:
    return max_workers >= 2 and n_selected >= 2


def _print_uncovered_if_needed(
    all_sites: list[Site],
    covered_lines: set[int],
    *,
    effective_since_last_run: bool,
    lines_filter: set[int] | None,
) -> None:
    if not effective_since_last_run and lines_filter is None:
        _print_lines(_uncovered_block_lines(all_sites, covered_lines))


def _write_manifest_output(
    clean_source: str,
    manifest: dict,
    loc: ManifestLocation,
    *,
    write_source: bool = True,
    write_manifest: bool = True,
) -> None:
    """Write clean_source/manifest to their configured storage (sidecar or in-source footer).

    In embed mode (loc.manifest_file is False) source and footer are always written
    together as one file, so write_source/write_manifest are ignored there.
    """
    if loc.manifest_file:
        if write_source:
            with open(loc.path, "w") as f:
                f.write(clean_source)
        if write_manifest:
            write_sidecar_manifest(loc.path, manifest)
    else:
        with open(loc.path, "w") as f:
            f.write(embed_manifest(clean_source, manifest))


def _finalize_source(
    clean_source: str,
    tested_at: str,
    bak_path: str,
    loc: ManifestLocation,
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
    _write_manifest_output(clean_source, manifest_to_embed, loc)
    if os.path.isfile(bak_path):
        os.remove(bak_path)


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


def run_scan(*, path: str, source: str, warning_threshold: int, coverage: CoverageSource) -> None:
    """Execute --scan: print site counts. Raises CoverageError on acquisition failure."""
    has_coverage = coverage.cov_cmd is not None or coverage.lcov_path is not None or coverage.reuse_coverage
    if has_coverage:
        lines, _ = scan_report_with_coverage(path, source, warning_threshold, coverage)
    else:
        lines, _ = scan_report(path, source, warning_threshold)
    print("\n".join(lines))


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
            print(f"Manifest unchanged: {path}")
            return 0
        _write_manifest_output(
            clean,
            manifest_to_embed,
            loc,
            write_source=source_has_stale_footer,
            write_manifest=manifest_changed,
        )
        print(f"Updated manifest: {path}")
        return 0

    if not manifest_changed:
        print(f"Manifest unchanged: {path}")
        return 0
    _write_manifest_output(clean, manifest_to_embed, loc)
    print(f"Updated manifest: {path}")
    return 0


def check_manifest(*, path: str, source: str, manifest_file: bool = False) -> int:
    """Check if the manifest in its configured storage is up to date. Returns 0 if current, 1 if stale or missing."""
    clean = strip_manifest(source)
    loc = ManifestLocation(path=path, manifest_file=manifest_file)
    existing, manifest_exists = _read_existing_manifest(source, loc)
    if not manifest_exists:
        print(f"Manifest missing: {path}")
        return 1
    existing_source_sha256 = existing.get("source_sha256")
    if existing_source_sha256 is not None and existing_source_sha256 == source_sha256(clean):
        print(f"Manifest current: {path}")
        return 0
    tested_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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


def _prepare_fork_server(*, requested: bool, test_command: str, cwd: str, guarded_path: str):
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
        print(f"note: fork-server fast path unavailable ({exc}); using the per-mutant subprocess model instead.")
        return None
    return server


def _fork_server_eligible(
    *,
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
    return fork_server_requested and not use_parallel and test_ctx_db is None and bool(selected_sites)


@dataclasses.dataclass
class LoadedSource:
    """The stripped source plus everything diffed against its prior manifest."""

    clean_source: str
    existing_manifest: dict | None
    manifest_exists: bool
    changed_fn_ids: set[str]
    tested_at: str
    all_sites: list[Site]
    changed_count: int


def _load_clean_source(bak_path: str, source: str, loc: ManifestLocation) -> LoadedSource:
    """Rescue from backup if needed, strip/diff the manifest, and discover sites."""
    rescued = _restore_from_backup(loc.path, bak_path)
    if rescued is not None:
        source = rescued
    (
        clean_source,
        existing_manifest,
        manifest_exists,
        changed_fn_ids,
        tested_at,
    ) = _compute_manifest_diff(source, loc)
    all_sites = discover_sites(clean_source)
    changed_count = len([s for s in all_sites if s.function_id in changed_fn_ids])
    return LoadedSource(
        clean_source=clean_source,
        existing_manifest=existing_manifest,
        manifest_exists=manifest_exists,
        changed_fn_ids=changed_fn_ids,
        tested_at=tested_at,
        all_sites=all_sites,
        changed_count=changed_count,
    )


@dataclasses.dataclass
class RunSetup:
    """Paths and loaded source state established before coverage/selection."""

    bak_path: str
    loc: ManifestLocation
    loaded: LoadedSource


def _prepare_run_setup(request: RunMutationsRequest) -> RunSetup:
    source_dir = os.path.dirname(os.path.abspath(request.path))
    bak_path = os.path.join(source_dir, os.path.basename(request.path) + ".bak")
    loc = ManifestLocation(path=request.path, manifest_file=request.manifest_file)
    loaded = _load_clean_source(bak_path, request.source, loc)
    return RunSetup(bak_path=bak_path, loc=loc, loaded=loaded)


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
    fork_server: object = None


def _select_and_prepare(
    request: RunMutationsRequest, setup: RunSetup, test_ctx_db, max_workers: int
) -> SelectionOutcome:
    """Acquire coverage, select sites, print the header, and prime the fork server.

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
        print(f"error: {cov_error}")
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
    _print_uncovered_if_needed(
        loaded.all_sites,
        covered_lines,
        effective_since_last_run=effective_since_last_run,
        lines_filter=request.lines_filter,
    )

    use_parallel = _should_run_parallel(max_workers, len(selected_sites))
    _print_lines(_workers_header_lines(max_workers, use_parallel=use_parallel, n_selected=len(selected_sites)))

    baseline_duration, baseline_error = _resolve_baseline_duration(
        request.baseline_duration, request.test_command, request.cwd
    )
    if baseline_error is not None:
        print(f"baseline failed: {baseline_error}")
        return SelectionOutcome(error_code=1)

    with open(setup.bak_path, "w") as f:
        f.write(loaded.clean_source)

    mutant_timeout = max(request.min_timeout, request.timeout_factor * baseline_duration)

    fork_server = _prepare_fork_server(
        requested=_fork_server_eligible(
            fork_server_requested=request.fork_server_requested,
            use_parallel=use_parallel,
            test_ctx_db=test_ctx_db,
            selected_sites=selected_sites,
        ),
        test_command=request.test_command,
        cwd=request.cwd,
        guarded_path=os.path.abspath(request.path),
    )

    return SelectionOutcome(
        selected_sites=selected_sites,
        uncovered_count=uncovered_count,
        use_parallel=use_parallel,
        max_workers=max_workers,
        mutant_timeout=mutant_timeout,
        fork_server=fork_server,
    )


def _resolve_baseline_duration(
    baseline_duration: float | None, test_command: str, cwd: str
) -> tuple[float | None, str | None]:
    """Return (duration, error). A pre-supplied duration is passed through untouched."""
    if baseline_duration is not None:
        return baseline_duration, None
    return run_baseline(test_command, cwd)


def run_mutations(request: RunMutationsRequest) -> int:
    """Execute the mutation run loop.

    Returns 0, 1 (coverage/baseline failure), or 2 (the test-context db and the
    LCOV coverage disagree about a selected site).
    """
    test_ctx_db, max_workers = _setup_test_context_db(request.test_contexts_path, request.max_workers)
    try:
        setup = _prepare_run_setup(request)
        outcome = _select_and_prepare(request, setup, test_ctx_db, max_workers)
        if outcome.error_code is not None:
            return outcome.error_code

        ctx = MutantExecCtx(
            path=request.path,
            cwd=request.cwd,
            test_command=request.test_command,
            mutant_timeout=outcome.mutant_timeout,
            max_workers=outcome.max_workers,
            use_parallel=outcome.use_parallel,
            abs_source_path=os.path.abspath(request.path),
            test_ctx_db=test_ctx_db,
            fork_server=outcome.fork_server,
        )
        finalize = FinalizeInputs(
            tested_at=setup.loaded.tested_at,
            bak_path=setup.bak_path,
            loc=setup.loc,
            existing_manifest=setup.loaded.existing_manifest,
        )

        return _execute_mutations(
            selected_sites=outcome.selected_sites,
            clean_source=setup.loaded.clean_source,
            ctx=ctx,
            uncovered_count=outcome.uncovered_count,
            finalize=finalize,
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
