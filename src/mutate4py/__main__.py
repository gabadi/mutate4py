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
    # `file` (singular) is not a flag: it's the resolved single-root scratch
    # field the legacy single-target dispatch functions read. Declaring it
    # here (rather than leaving `_dispatch` inject it unannounced) gives it
    # a static home; `_dispatch` is the one place that populates it, from
    # `files` (plural, the actual positional) via `_expand_roots`.
    parser.set_defaults(file=None)
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


def _collect_py_files(directory: str, exclude: Sequence[str] = ()) -> list[str]:
    """The .py files under a root, minus --exclude matches.

    The root may be a directory (walked recursively) or a single file (kept
    as-is if it survives the same filter) — the union path (issue #22 item
    15) calls this uniformly over every resolved root.
    """
    if not os.path.isdir(directory):
        return [directory] if _is_target_py_file(directory, exclude) else []
    result = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = _walkable_dirs(dirs)
        for f in sorted(files):
            path = os.path.join(root, f)
            if _is_target_py_file(path, exclude):
                result.append(path)
    return result


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
    """The directory's .py files minus --exclude matches; exit 2 if none remain."""
    files = _collect_py_files(args.file, args.exclude or ())
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
        files.extend(_collect_py_files(root, args.exclude or ()))
    files = _dedup_by_realpath(files)
    if args.verbose:
        for root in roots:
            _report_excluded(root, files)
    if not files:
        _exit_no_files()
    return files


def _run_files_and_exit(args: argparse.Namespace, files: list[str]) -> None:
    """Run the configured mode over each file; exit 1 if any file failed."""
    cwd = os.getcwd()
    baseline_duration = None
    if _needs_directory_baseline(files, args):
        baseline_duration = _prepare_directory_baseline(args, files, cwd)
    exit_code = 0
    for py_file in files:
        if (
            _run_on_file(args, py_file, _load_source(py_file), cwd, baseline_duration)
            != 0
        ):
            exit_code = 1
    sys.exit(exit_code)


def _dispatch_directory(args: argparse.Namespace) -> None:
    _run_files_and_exit(args, _directory_files(args))


def _dispatch_union(args: argparse.Namespace, roots: list[str]) -> None:
    """Two or more resolved roots: one baseline, one exit code (item 2)."""
    _run_files_and_exit(args, _collect_union_files(args, roots))


def _dispatch_single_file(args: argparse.Namespace, source: str, cwd: str) -> None:
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


def _merge_workspace_excludes(existing: Sequence[str] | None) -> list[str]:
    """--exclude patterns plus one "prune this subtree" pattern per
    directory named by [tool.uv.workspace].exclude (item 10's second half:
    the recursive workspace-root walk, not just the member list)."""
    patterns = list(existing or ())
    patterns.extend(f"{d}/**" for d in _workspace_exclude_dirs())
    return patterns


def _resolve_roots(args: argparse.Namespace) -> list[str]:
    """Positionals/globs, or uv workspace autodiscovery when none are given
    (issue #22 item 3). Autodiscovery also folds [tool.uv.workspace].exclude
    into args.exclude so the shared collector prunes it from every walk."""
    if args.files:
        return _expand_roots(args.files)
    roots = _discover_workspace_roots()
    args.exclude = _merge_workspace_excludes(args.exclude)
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
    _dispatch_single_file(args, source, os.getcwd())


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _check_coverage_flags(args)
    _validate_mutual_exclusions(args)
    _check_test_contexts_file(args)
    _dispatch(args)


if __name__ == "__main__":
    main()


# mutate4py-manifest-begin
# {"version":1,"tested_at":"2026-08-05T15:48:14Z","module_hash":"3ffe25520e6896c63b21612991bd6c9a9b700f5f9e8b55660cc74a4c36f970c7","functions":[{"id":"func/_positive_int","name":"_positive_int","line":23,"end_line":31,"hash":"06de4d3f74cf39cb40383657b49523cefc38cdf8566d5f8125553f3fd3c195d3"},{"id":"func/_build_parser","name":"_build_parser","line":34,"end_line":163,"hash":"04647a129963ae7d24e6d575cf709ac46dcf8641f974e5e0d39b20ca0f669aeb"},{"id":"func/_check_coverage_flags","name":"_check_coverage_flags","line":166,"end_line":175,"hash":"42edc6617a1e291bd93d3578d7e32e708f713f9084ccba6be2331ad9b0ec9f87"},{"id":"func/_no_run_flag","name":"_no_run_flag","line":178,"end_line":184,"hash":"59aa486011c3e3158e11848b3f49b3182be927b8b3fc1c89b7b93890a7470ba9"},{"id":"func/_exit_incompatible","name":"_exit_incompatible","line":187,"end_line":189,"hash":"db2fe36913cbe87d3616570466315a8988310564ec93851dc7290d8065b8cee0"},{"id":"func/_check_no_run_incompatibilities","name":"_check_no_run_incompatibilities","line":192,"end_line":204,"hash":"53d50c7e588b2c2c608132917c7e016812ad25cb7f5f8fa6780e4a91ace9431b"},{"id":"func/_check_scan_only_incompatibilities","name":"_check_scan_only_incompatibilities","line":207,"end_line":214,"hash":"77d8a7f28df92300239bc3881b089c51438d9dafd77dd134a1e01964e4d24ada"},{"id":"func/_check_selection_exclusivity","name":"_check_selection_exclusivity","line":217,"end_line":228,"hash":"6ff1d994acd05c8dac1f9d7c4467a6fc74aa37899720361f85876e0f79a40e26"},{"id":"func/_validate_mutual_exclusions","name":"_validate_mutual_exclusions","line":231,"end_line":245,"hash":"6155e6243361768bcdfd18a457def365adbf180f8e41ac3f9e6497e59fe6790b"},{"id":"func/_load_source","name":"_load_source","line":248,"end_line":255,"hash":"b5c0322beb2e960c86d48fc3d00b8e1a910b64d4cfcadc414911fbcac6c7cc04"},{"id":"func/_parse_line_token","name":"_parse_line_token","line":258,"end_line":273,"hash":"3ede4fa8f423d5d27e97f3e7c6aec920c3e2e308159c05b42643d0c474b7fb86"},{"id":"func/_parse_lines","name":"_parse_lines","line":276,"end_line":281,"hash":"4febad296c3c5be36594a0188127548ab4edcba48a3bd946848e9c583b398ac4"},{"id":"func/_run_scan","name":"_run_scan","line":284,"end_line":298,"hash":"8075b51b362f0442df434fb5830df8d0de03eeb295e4bd0b1354700c6c9e29df"},{"id":"func/_is_excluded","name":"_is_excluded","line":301,"end_line":303,"hash":"008bb3479fed6ab60747c3e91f15586b27714a78f41dcc0a316c1f3fb437333c"},{"id":"func/_walkable_dirs","name":"_walkable_dirs","line":309,"end_line":317,"hash":"4f22c58112ba0afe1555a5cfcc33620783628b651b8d04334b478761246378c8"},{"id":"func/_is_target_py_file","name":"_is_target_py_file","line":320,"end_line":322,"hash":"69b7f59a350fc254d4684e754664f855fe5f092751a06d14950ce0f6850dee10"},{"id":"func/_collect_py_files","name":"_collect_py_files","line":325,"end_line":341,"hash":"962f63faeea28c326d3c10308ab639cb06de1ddc92d35b17a0a26f752f2b278c"},{"id":"func/_has_glob_chars","name":"_has_glob_chars","line":347,"end_line":349,"hash":"703845b0b8f13e5b7e1948c1aa1d938ef78417edc414fef146d35eee2f98faf7"},{"id":"func/_exit_pattern_no_match","name":"_exit_pattern_no_match","line":352,"end_line":354,"hash":"84641a5d71225a0607c582d53b4fff00526dc2e17110aa0c2f294b86c567e2b6"},{"id":"func/_exit_path_not_found","name":"_exit_path_not_found","line":357,"end_line":359,"hash":"5ee48ed55bb3bd40b55bd69648587841818f4b1bb5f18b74713e1d6955ef93f2"},{"id":"func/_expand_glob_pattern","name":"_expand_glob_pattern","line":362,"end_line":372,"hash":"62eac99b3fbea8b706b263de66ddf3e0ee2c0e8b0e25eac89693e3f903ce6667"},{"id":"func/_expand_literal_path","name":"_expand_literal_path","line":375,"end_line":379,"hash":"7579eec406753238a65caee97bf99108058e86d23482ef1d89bedd5cd125ddc8"},{"id":"func/_expand_roots","name":"_expand_roots","line":382,"end_line":396,"hash":"ba5c6bdaedd5f79a4bffc00336ee81773b92a588f409ec9578f5bfbbcbdbbb5a"},{"id":"func/_dedup_by_realpath","name":"_dedup_by_realpath","line":399,"end_line":409,"hash":"87e85ddc47d1cf35c9d33e0bb3c385a32fb725c0267e4f35f424cca6e341d296"},{"id":"func/_run_on_file","name":"_run_on_file","line":412,"end_line":461,"hash":"dd7080b90f6869ae98138abbefaeee5fc92eccab73b6932a855e432a3266d1b0"},{"id":"func/_needs_directory_baseline","name":"_needs_directory_baseline","line":464,"end_line":468,"hash":"5d52f1c4f16dafb723d1963e0b2dc0e8aa625d0c3fe72a339d9c711bffe48a51"},{"id":"func/_prepare_directory_baseline","name":"_prepare_directory_baseline","line":471,"end_line":495,"hash":"811f2e34fd3d23c47aafd1c0e685a6ded294a940ea0873332b5411777396df3a"},{"id":"func/_exit_no_files","name":"_exit_no_files","line":498,"end_line":501,"hash":"9ca598450062e7d4708f9e70853456519e11ffb6217fd5644e3f5a76b342a17d"},{"id":"func/_report_excluded","name":"_report_excluded","line":504,"end_line":509,"hash":"d39d12cabc42914121f14c1bdaa74b750cafa3e89b9bc0699a6bf216387027c1"},{"id":"func/_directory_files","name":"_directory_files","line":512,"end_line":519,"hash":"7c319b9bb7366330cb8c63221651c8d1f96fb5e9c8a95309d654f476953287ee"},{"id":"func/_collect_union_files","name":"_collect_union_files","line":522,"end_line":534,"hash":"cfd8ee7037e2d75d1f10e5a27cd97cc6b93f15de26bc9058a55dc5b9bb53ebec"},{"id":"func/_run_files_and_exit","name":"_run_files_and_exit","line":537,"end_line":550,"hash":"99ebe94caae5b3db57ab29991027f9c4085105cd1d1cbe9a89a674df1f454d8a"},{"id":"func/_dispatch_directory","name":"_dispatch_directory","line":553,"end_line":554,"hash":"cd9fe0a07f1d93d8209a32a143d3bf72bb71ddac2087c73a27879e0a4f352c5e"},{"id":"func/_dispatch_union","name":"_dispatch_union","line":557,"end_line":559,"hash":"39ba08ec735b348a640ef683f3a19572ecbc0cf7bbc1fb67193ac6003f6401bc"},{"id":"func/_dispatch_single_file","name":"_dispatch_single_file","line":562,"end_line":596,"hash":"8aec4e9b86461dd262a69ef6ec4c8e8de87ca63b0f27a8c8d6a326a1fc0727e2"},{"id":"func/_exit_if_target_excluded","name":"_exit_if_target_excluded","line":599,"end_line":605,"hash":"dc1547a78ec13ffde683fff66f28f0ddc0186e8ff601f2c743b04ddc3f62442d"},{"id":"func/_check_test_contexts_file","name":"_check_test_contexts_file","line":608,"end_line":614,"hash":"01d041e6fd839104df12dd20d9ca31c1081c13c694afab66bcdee3bcccd90cf0"},{"id":"func/_merge_workspace_excludes","name":"_merge_workspace_excludes","line":617,"end_line":623,"hash":"e83bf273d895d59cedf661af488dbe0f0ee813a74d4848757b90e9796be41088"},{"id":"func/_resolve_roots","name":"_resolve_roots","line":626,"end_line":634,"hash":"c93772017a4c87d0fa5b337f23d764a5f4c2109199363184eea829941f11283c"},{"id":"func/_dispatch","name":"_dispatch","line":637,"end_line":656,"hash":"3cc0c8c4a70a12512fc39ed6b6ba0e05bbfee1f8c6a76abbb5e074b2594ebbf7"},{"id":"func/main","name":"main","line":659,"end_line":665,"hash":"06593c291a934abb9e592ac30b9f1fbd24e6cb66dd970e9a4f0ab56925cf68b6"}]}
# mutate4py-manifest-end
