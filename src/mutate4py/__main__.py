"""CLI entry point for mutate4py."""

import argparse
import glob
import os
import sys
from collections.abc import Sequence

from mutate4py._glob_dialect import glob_match
from mutate4py._runner import (
    CoverageError,
    check_manifest,
    run_baseline,
    run_mutations,
    run_scan,
    update_manifest,
)
from mutate4py._workspace import _discover_workspace_roots, _workspace_exclude_dirs

DEFAULT_WARNING_THRESHOLD = 50


def _positive_int(value: str) -> int:
    """argparse type: parse a positive integer (>= 1)."""
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a valid integer")
    if n < 1:
        raise argparse.ArgumentTypeError(f"{value!r} must be a positive integer (>= 1)")
    return n


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mutate4py",
        description="Mutation testing for Python with an embedded-in-source manifest",
    )
    parser.add_argument(
        "files",
        nargs="*",
        metavar="PATH",
        help="Python source file(s), directories, or glob patterns to analyse "
        "('*' matches one path segment, '**' matches zero or more). "
        "Two or more resolved paths run as one union batch, one exit code. "
        "Omit entirely to autodiscover a uv workspace from the current "
        "directory upward (the workspace root plus its member packages).",
    )
    parser.add_argument(
        "--scan", action="store_true", help="Count mutation sites; no test run"
    )
    parser.add_argument(
        "--mutation-warning",
        type=_positive_int,
        default=DEFAULT_WARNING_THRESHOLD,
        dest="warning_threshold",
        help="Warn when mutation sites exceed N (default: 50)",
    )
    parser.add_argument(
        "--update-manifest",
        action="store_true",
        help="Embed or refresh the manifest footer in the source file; no test run",
    )
    parser.add_argument(
        "--check-manifest",
        action="store_true",
        dest="check_manifest",
        help="Verify the manifest footer is up to date; exit 1 if missing or stale; no test run",
    )
    parser.add_argument(
        "--manifest-file",
        action="store_true",
        dest="manifest_file",
        help="Store the manifest as sidecar JSON (<file>.manifest.json) next to "
        "each source file instead of embedding it in the source file",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        dest="exclude",
        default=None,
        help="Skip files whose path matches PATTERN "
        "('*' matches one path segment, '**' matches zero or more; repeatable)",
    )
    parser.add_argument(
        "--cov-cmd",
        dest="cov_cmd",
        default=None,
        help="Shell command to run once to generate LCOV coverage",
    )
    parser.add_argument(
        "--lcov", dest="lcov", default=None, help="Path to a pre-generated LCOV file"
    )
    parser.add_argument(
        "--reuse-coverage",
        action="store_true",
        dest="reuse_coverage",
        help="Read LCOV from coverage.lcov (default path)",
    )
    parser.add_argument(
        "--test-command",
        dest="test_command",
        default="pytest",
        help="Command to run tests (default: pytest)",
    )
    parser.add_argument(
        "--timeout-factor",
        type=_positive_int,
        default=10,
        dest="timeout_factor",
        help="Mutant timeout = max(--min-timeout, factor × baseline duration) (default: 10)",
    )
    parser.add_argument(
        "--min-timeout",
        type=float,
        default=1.0,
        dest="min_timeout",
        help="Floor for mutant timeout in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--lines",
        dest="lines",
        default=None,
        help="Comma-separated line numbers to mutate",
    )
    parser.add_argument(
        "--since-last-run",
        action="store_true",
        dest="since_last_run",
        help="Only mutate sites in changed functions",
    )
    parser.add_argument(
        "--mutate-all",
        action="store_true",
        dest="mutate_all",
        help="Mutate all covered sites regardless of manifest",
    )
    parser.add_argument(
        "--max-workers",
        type=_positive_int,
        default=None,
        dest="max_workers",
        help="Number of parallel workers; omit or 0 = serial (default: serial)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        dest="verbose",
        help="Log actions to stderr",
    )
    parser.add_argument(
        "--test-contexts",
        dest="test_contexts",
        default=None,
        help="Path to a .coverage SQLite db (pytest --cov-context=test); enables per-mutant test selection",
    )
    parser.add_argument(
        "--no-fork-server",
        action="store_true",
        dest="no_fork_server",
        help="Disable the fork-server fast path (on by default for serial runs "
        "with a plain `pytest` --test-command on a POSIX platform; it falls "
        "back to a fresh subprocess per mutant automatically wherever it "
        "isn't safe or applicable, so this is only needed to force the old "
        "behavior, e.g. for debugging)",
    )
    # `file` (singular) is not a flag: it's the resolved single-root scratch
    # field the legacy single-target dispatch functions read. Declaring it
    # here (rather than leaving `_dispatch` inject it unannounced) gives it
    # a static home; `_dispatch` is the one place that populates it, from
    # `files` (plural, the actual positional) via `_expand_roots`.
    # `prune_dirs` is likewise not a flag: workspace autodiscovery populates
    # it with real [tool.uv.workspace].exclude directories for _collect_py_files
    # to skip by path identity; every other run leaves it empty.
    parser.set_defaults(file=None, prune_dirs=())
    return parser


def _check_coverage_flags(args: argparse.Namespace) -> None:
    """Exit with error if more than one coverage flag is supplied (ADR 0008)."""
    cov_flags = [args.cov_cmd is not None, args.lcov is not None, args.reuse_coverage]
    if sum(cov_flags) > 1:
        print(
            "error: --cov-cmd, --lcov, and --reuse-coverage are mutually exclusive; "
            "supply at most one.",
            file=sys.stderr,
        )
        sys.exit(2)


def _no_run_flag(args: argparse.Namespace) -> str:
    """Return the active no-run flag name for error messages."""
    if args.scan:
        return "--scan"
    if args.update_manifest:
        return "--update-manifest"
    return "--check-manifest"


def _exit_incompatible(flag_a: str, flag_b: str) -> None:
    print(f"error: {flag_a} cannot be combined with {flag_b}.", file=sys.stderr)
    sys.exit(2)


def _check_no_run_incompatibilities(args: argparse.Namespace) -> None:
    """Exit if run-mode flags are paired with no-run-mode flags."""
    flag = _no_run_flag(args)
    if args.lines is not None:
        _exit_incompatible(flag, "--lines")
    if args.since_last_run:
        _exit_incompatible(flag, "--since-last-run")
    if args.mutate_all:
        _exit_incompatible(flag, "--mutate-all")
    if args.max_workers is not None:
        _exit_incompatible(flag, "--max-workers")
    if args.test_contexts is not None:
        _exit_incompatible(flag, "--test-contexts")


def _check_scan_only_incompatibilities(args: argparse.Namespace) -> None:
    """Exit if scan-only flags are paired with non-scan flags."""
    if args.timeout_factor != 10:
        _exit_incompatible("--scan", "--timeout-factor")
    if args.min_timeout != 1.0:
        _exit_incompatible("--scan", "--min-timeout")
    if args.test_command != "pytest":
        _exit_incompatible("--scan", "--test-command")


def _check_selection_exclusivity(args: argparse.Namespace) -> None:
    """Exit if more than one selection flag is set."""
    selection_count = sum(
        [args.since_last_run, args.mutate_all, args.lines is not None]
    )
    if selection_count > 1:
        print(
            "error: --since-last-run, --mutate-all, and --lines are pairwise exclusive; "
            "supply at most one.",
            file=sys.stderr,
        )
        sys.exit(2)


def _validate_mutual_exclusions(args: argparse.Namespace) -> None:
    """Exit with error on illegal flag combinations (ADR 0008, 0014)."""
    no_run = [
        ("--scan", args.scan),
        ("--update-manifest", args.update_manifest),
        ("--check-manifest", args.check_manifest),
    ]
    active = [name for name, v in no_run if v]
    if len(active) > 1:
        _exit_incompatible(active[0], active[1])
    if active:
        _check_no_run_incompatibilities(args)
        if args.scan:
            _check_scan_only_incompatibilities(args)
    _check_selection_exclusivity(args)


def _load_source(path: str) -> str:
    """Read source file; exit with error if unreadable."""
    try:
        with open(path) as f:
            return f.read()
    except (FileNotFoundError, PermissionError, IsADirectoryError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)


def _syntax_error_reason(exc: SyntaxError) -> str:
    """Human-readable reason for a SyntaxError, independent of ast.parse's filename."""
    if exc.lineno is not None:
        return f"{exc.msg} (line {exc.lineno})"
    return exc.msg


def _report_parse_error(path: str, exc: SyntaxError) -> None:
    print(f"error: cannot parse {path}: {_syntax_error_reason(exc)}", file=sys.stderr)


def _parse_line_token(token: str) -> int:
    """Parse a single --lines token into a positive int; exit on error."""
    try:
        n = int(token)
    except ValueError:
        print(
            f"error: --lines value {token!r} is not a valid integer.", file=sys.stderr
        )
        sys.exit(2)
    if n < 1:
        print(
            f"error: --lines value {token!r} must be a positive integer (>= 1).",
            file=sys.stderr,
        )
        sys.exit(2)
    return n


def _parse_lines(lines_str: str | None) -> set[int] | None:
    """Parse --lines argument into a set of positive ints, or None if not given."""
    if lines_str is None:
        return None
    parts = [p.strip() for p in lines_str.split(",") if p.strip()]
    return {_parse_line_token(p) for p in parts}


def _run_scan(args: argparse.Namespace, source: str, cwd: str) -> None:
    """Execute --scan logic; exits with code 2 on CoverageError."""
    try:
        run_scan(
            path=args.file,
            source=source,
            warning_threshold=args.warning_threshold,
            cov_cmd=args.cov_cmd,
            lcov_path=args.lcov,
            reuse_coverage=args.reuse_coverage,
            cwd=cwd,
        )
    except CoverageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)


def _is_excluded(path: str, patterns: Sequence[str]) -> bool:
    """True if path matches any --exclude glob (shared dialect, case-sensitive)."""
    return any(glob_match(path, pattern) for pattern in patterns)


_PRUNED_DIR_NAMES = {"__pycache__", "venv", "node_modules"}


def _walkable_dirs(dirs: list[str]) -> list[str]:
    """Sorted subdirectories to descend into.

    Prunes __pycache__, venv, node_modules, and any dot-directory (e.g.
    .git, .venv). build/ and dist/ are deliberately left walkable.
    """
    return sorted(
        d for d in dirs if d not in _PRUNED_DIR_NAMES and not d.startswith(".")
    )


def _is_target_py_file(path: str, exclude: Sequence[str]) -> bool:
    """True for a .py file that no --exclude pattern drops."""
    return path.endswith(".py") and not _is_excluded(path, exclude)


def _prune_walk_dirs(root: str, dirs: list[str], pruned_real: set[str]) -> list[str]:
    """Walkable subdirectories of root, minus any whose realpath is pruned."""
    return [
        d
        for d in _walkable_dirs(dirs)
        if os.path.realpath(os.path.join(root, d)) not in pruned_real
    ]


def _walk_py_files(
    directory: str, exclude: Sequence[str], pruned_real: set[str]
) -> list[str]:
    result = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = _prune_walk_dirs(root, dirs, pruned_real)
        for f in sorted(files):
            path = os.path.join(root, f)
            if _is_target_py_file(path, exclude):
                result.append(path)
    return result


def _collect_py_files(
    directory: str, exclude: Sequence[str] = (), prune_dirs: Sequence[str] = ()
) -> list[str]:
    """The .py files under a root, minus --exclude matches and any pruned
    subtree.

    The root may be a directory (walked recursively) or a single file (kept
    as-is if it survives the same filter) — the union path (issue #22 item
    15) calls this uniformly over every resolved root.

    prune_dirs skips whole subtrees by path identity (os.path.realpath),
    not by glob pattern — used for [tool.uv.workspace].exclude, which names
    real directories that may themselves contain glob metacharacters (phase
    B review: a literal "*" in a directory name must not be reinterpreted).
    """
    if not os.path.isdir(directory):
        return [directory] if _is_target_py_file(directory, exclude) else []
    pruned_real = {os.path.realpath(d) for d in prune_dirs}
    return _walk_py_files(directory, exclude, pruned_real)


_GLOB_CHARS = frozenset("*?[")


def _has_glob_chars(pattern: str) -> bool:
    """True if pattern needs filesystem expansion rather than literal lookup."""
    return any(c in _GLOB_CHARS for c in pattern)


def _exit_pattern_no_match(pattern: str) -> None:
    print(f"error: pattern {pattern!r} matched no files.", file=sys.stderr)
    sys.exit(2)


def _exit_path_not_found(pattern: str) -> None:
    print(f"error: [Errno 2] No such file or directory: {pattern!r}", file=sys.stderr)
    sys.exit(2)


def _expand_glob_pattern(pattern: str) -> list[str]:
    """Resolve a wildcard pattern to its matched dirs/.py files, sorted.

    Other matched files are dropped silently (issue #22 item 6); if nothing
    survives, exits 2 naming the pattern (item 7).
    """
    matches = sorted(glob.glob(pattern, recursive=True))
    kept = [m for m in matches if os.path.isdir(m) or m.endswith(".py")]
    if not kept:
        _exit_pattern_no_match(pattern)
    return kept


def _expand_literal_path(pattern: str) -> str:
    """Resolve a literal (non-wildcard) path; exits 2 naming it if missing."""
    if not os.path.exists(pattern):
        _exit_path_not_found(pattern)
    return pattern


def _expand_roots(patterns: Sequence[str]) -> list[str]:
    """Resolve positional patterns to root paths, in argument order.

    Every pattern is validated (item 7's fail-fast) before any file is
    collected: a bad pattern anywhere in the list exits 2 before dispatch,
    with none of the other patterns' files processed. Feeds both positional
    expansion (this cycle) and uv workspace `members` (a later cycle).
    """
    roots: list[str] = []
    for pattern in patterns:
        if _has_glob_chars(pattern):
            roots.extend(_expand_glob_pattern(pattern))
        else:
            roots.append(_expand_literal_path(pattern))
    return roots


def _dedup_by_realpath(files: list[str]) -> list[str]:
    """Drop later duplicates that resolve to the same real path; keep the
    first occurrence and the given order (issue #22 item 14)."""
    seen: set[str] = set()
    result = []
    for f in files:
        real = os.path.realpath(f)
        if real not in seen:
            seen.add(real)
            result.append(f)
    return result


def _run_on_file(
    args: argparse.Namespace,
    py_file: str,
    source: str,
    cwd: str,
    baseline_duration: float | None = None,
) -> int:
    if args.check_manifest:
        return check_manifest(
            path=py_file, source=source, manifest_file=args.manifest_file
        )
    if args.update_manifest:
        update_manifest(path=py_file, source=source, manifest_file=args.manifest_file)
        return 0
    if args.scan:
        try:
            run_scan(
                path=py_file,
                source=source,
                warning_threshold=args.warning_threshold,
                cov_cmd=args.cov_cmd,
                lcov_path=args.lcov,
                reuse_coverage=args.reuse_coverage,
                cwd=cwd,
            )
        except CoverageError as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(2)
        return 0
    lines_filter = _parse_lines(args.lines)
    max_workers = args.max_workers if args.max_workers is not None else 0
    return run_mutations(
        path=py_file,
        source=source,
        cov_cmd=args.cov_cmd,
        lcov_path=args.lcov,
        reuse_coverage=args.reuse_coverage,
        test_command=args.test_command,
        timeout_factor=args.timeout_factor,
        min_timeout=args.min_timeout,
        lines_filter=lines_filter,
        since_last_run=args.since_last_run,
        mutate_all=args.mutate_all,
        warning_threshold=args.warning_threshold,
        max_workers=max_workers,
        cwd=cwd,
        baseline_duration=baseline_duration,
        test_contexts_path=args.test_contexts,
        manifest_file=args.manifest_file,
        fork_server_requested=not args.no_fork_server,
    )


def _needs_directory_baseline(files: list[str], args: argparse.Namespace) -> bool:
    """A shared baseline is only needed when the run will actually execute mutants."""
    return bool(files) and not (
        args.scan or args.update_manifest or args.check_manifest
    )


def _prepare_directory_baseline(
    args: argparse.Namespace, files: list[str], cwd: str
) -> float:
    """Acquire coverage once and time the baseline for a directory run.

    Exits the process on failure, matching the single-file dispatch behavior.
    """
    from mutate4py._coverage import acquire_coverage

    try:
        acquire_coverage(
            cov_cmd=args.cov_cmd,
            lcov_path=args.lcov,
            reuse=args.reuse_coverage,
            cwd=cwd,
            source_path=os.path.abspath(files[0]),
        )
    except CoverageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    baseline_duration, baseline_error = run_baseline(args.test_command, cwd)
    if baseline_error is not None:
        print(f"baseline failed: {baseline_error}", file=sys.stderr)
        sys.exit(1)
    return baseline_duration


def _exit_no_files() -> None:
    """Exit 2 when nothing is left to process (empty tree, or all excluded)."""
    print("error: no Python files to process.", file=sys.stderr)
    sys.exit(2)


def _report_excluded(directory: str, kept: list[str]) -> None:
    """Print one line per file --exclude dropped from the walk (--verbose only)."""
    keep = set(kept)
    for path in _collect_py_files(directory):
        if path not in keep:
            print(f"Excluded: {path}")


def _directory_files(args: argparse.Namespace) -> list[str]:
    """The directory's .py files minus --exclude matches and any pruned
    subtree; exit 2 if none remain."""
    files = _collect_py_files(args.file, args.exclude or (), args.prune_dirs)
    if args.verbose:
        _report_excluded(args.file, files)
    if not files:
        _exit_no_files()
    return files


def _collect_union_files(args: argparse.Namespace, roots: list[str]) -> list[str]:
    """The union's .py files across all roots: root order, deduped, exit 2 if
    the whole union is empty (an individual empty root is silent, item 17)."""
    files: list[str] = []
    for root in roots:
        files.extend(_collect_py_files(root, args.exclude or (), args.prune_dirs))
    files = _dedup_by_realpath(files)
    if args.verbose:
        for root in roots:
            _report_excluded(root, files)
    if not files:
        _exit_no_files()
    return files


def _run_files_and_exit(args: argparse.Namespace, files: list[str]) -> None:
    """Run the configured mode over every file; exit with the worst (highest)
    per-file code seen, so a selection disagreement (2) is never flattened into
    an ordinary failure (1). A failing file never stops the batch — including a
    file that fails to parse, which contributes code 2 and is tallied into the
    trailing parse-failure summary line."""
    cwd = os.getcwd()
    baseline_duration = None
    if _needs_directory_baseline(files, args):
        baseline_duration = _prepare_directory_baseline(args, files, cwd)
    exit_code = 0
    parse_failures = 0
    for py_file in files:
        try:
            exit_code = max(
                exit_code,
                _run_on_file(
                    args, py_file, _load_source(py_file), cwd, baseline_duration
                ),
            )
        except SyntaxError as exc:
            _report_parse_error(py_file, exc)
            exit_code = max(exit_code, 2)
            parse_failures += 1
    if parse_failures:
        print(f"error: {parse_failures} files could not be parsed", file=sys.stderr)
    sys.exit(exit_code)


def _dispatch_directory(args: argparse.Namespace) -> None:
    _run_files_and_exit(args, _directory_files(args))


def _dispatch_union(args: argparse.Namespace, roots: list[str]) -> None:
    """Two or more resolved roots: one shared baseline, and one exit code — the
    worst per-file code across the union (item 2)."""
    _run_files_and_exit(args, _collect_union_files(args, roots))


def _dispatch_single_file(args: argparse.Namespace, source: str, cwd: str) -> None:
    """Route a single-file target by mode; lets SyntaxError propagate to the
    caller, which reports it (issue #35 — same contract as the batch path)."""
    if args.check_manifest:
        sys.exit(
            check_manifest(
                path=args.file, source=source, manifest_file=args.manifest_file
            )
        )
    if args.scan:
        _run_scan(args, source, cwd)
        return
    if args.update_manifest:
        update_manifest(path=args.file, source=source, manifest_file=args.manifest_file)
        return
    lines_filter = _parse_lines(args.lines)
    max_workers = args.max_workers if args.max_workers is not None else 0
    sys.exit(
        run_mutations(
            path=args.file,
            source=source,
            cov_cmd=args.cov_cmd,
            lcov_path=args.lcov,
            reuse_coverage=args.reuse_coverage,
            test_command=args.test_command,
            timeout_factor=args.timeout_factor,
            min_timeout=args.min_timeout,
            lines_filter=lines_filter,
            since_last_run=args.since_last_run,
            mutate_all=args.mutate_all,
            warning_threshold=args.warning_threshold,
            max_workers=max_workers,
            cwd=cwd,
            test_contexts_path=args.test_contexts,
            manifest_file=args.manifest_file,
            fork_server_requested=not args.no_fork_server,
        )
    )


def _exit_if_target_excluded(args: argparse.Namespace) -> None:
    """Exit 2 when the single-file target itself matches an --exclude pattern."""
    if not _is_excluded(args.file, args.exclude or ()):
        return
    if args.verbose:
        print(f"Excluded: {args.file}")
    _exit_no_files()


def _check_test_contexts_file(args: argparse.Namespace) -> None:
    if args.test_contexts is not None and not os.path.isfile(args.test_contexts):
        print(
            f"error: --test-contexts file not found: {args.test_contexts}",
            file=sys.stderr,
        )
        sys.exit(2)


def _resolve_roots(args: argparse.Namespace) -> list[str]:
    """Positionals/globs, or uv workspace autodiscovery when none are given
    (issue #22 item 3). Autodiscovery also sets args.prune_dirs to the real
    [tool.uv.workspace].exclude directories, so the shared collector skips
    them by path identity in every walk (item 10's second half) — not by
    re-encoding a literal directory path as a glob pattern, which a "*" in
    the directory's own name would misinterpret."""
    if args.files:
        return _expand_roots(args.files)
    roots = _discover_workspace_roots()
    args.prune_dirs = _workspace_exclude_dirs()
    return roots


def _dispatch(args: argparse.Namespace) -> None:
    """Resolve positionals (or autodiscover a workspace), then route by
    arity (issue #22 item 2).

    Exactly one resolved path reuses today's single-file/directory dispatch,
    untouched; two or more run as one union batch.
    """
    roots = _resolve_roots(args)
    if len(roots) > 1:
        _dispatch_union(args, roots)
        return
    # Populates the args.file scratch field declared in _build_parser; every
    # legacy single-target function below reads it from here.
    args.file = roots[0]
    if os.path.isdir(args.file):
        _dispatch_directory(args)
        return
    source = _load_source(args.file)  # a bad path must report itself, not "excluded"
    _exit_if_target_excluded(args)
    try:
        _dispatch_single_file(args, source, os.getcwd())
    except SyntaxError as exc:
        _report_parse_error(args.file, exc)
        sys.exit(2)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _check_coverage_flags(args)
    _validate_mutual_exclusions(args)
    _check_test_contexts_file(args)
    _dispatch(args)


if __name__ == "__main__":
    main()


# {"version":1,"tested_at":"2026-08-09T03:03:31Z","module_hash":"13abbb279d419a7af52c2d9e76e2d6783abc08d794ac74e49ff6606a5f7aae2e","functions":[]}
# mutate4py-manifest-end
