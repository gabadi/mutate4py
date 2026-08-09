"""CLI entry point for mutate4py."""

import argparse
import os
import sys

from mutate4py._runner import (
    CoverageError,
    CoverageSource,
    RunMutationsRequest,
    check_manifest,
    run_baseline,
    run_mutations,
    run_scan,
    update_manifest,
)
from mutate4py._target_resolution import (
    NoFilesToProcessError,
    TargetResolutionError,
    _collect_py_files,
    _dedup_by_realpath,
    _expand_roots,
    _is_excluded,
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
    parser.add_argument("--scan", action="store_true", help="Count mutation sites; no test run")
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
    parser.add_argument("--lcov", dest="lcov", default=None, help="Path to a pre-generated LCOV file")
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
            "error: --cov-cmd, --lcov, and --reuse-coverage are mutually exclusive; supply at most one.",
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
    selection_count = sum([args.since_last_run, args.mutate_all, args.lines is not None])
    if selection_count > 1:
        print(
            "error: --since-last-run, --mutate-all, and --lines are pairwise exclusive; supply at most one.",
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
        print(f"error: --lines value {token!r} is not a valid integer.", file=sys.stderr)
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


def _run_scan(args: argparse.Namespace, path: str, source: str, cwd: str) -> None:
    """Execute --scan logic; exits with code 2 on CoverageError."""
    try:
        run_scan(
            path=path,
            source=source,
            warning_threshold=args.warning_threshold,
            coverage=CoverageSource(
                cov_cmd=args.cov_cmd,
                lcov_path=args.lcov,
                reuse_coverage=args.reuse_coverage,
                cwd=cwd,
            ),
        )
    except CoverageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)


def _run_on_file(
    args: argparse.Namespace,
    py_file: str,
    source: str,
    cwd: str,
    baseline_duration: float | None = None,
) -> int:
    if args.check_manifest:
        return check_manifest(path=py_file, source=source, manifest_file=args.manifest_file)
    if args.update_manifest:
        update_manifest(path=py_file, source=source, manifest_file=args.manifest_file)
        return 0
    if args.scan:
        _run_scan(args, py_file, source, cwd)
        return 0
    lines_filter = _parse_lines(args.lines)
    max_workers = args.max_workers if args.max_workers is not None else 0
    return run_mutations(
        RunMutationsRequest(
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
    )


def _needs_directory_baseline(files: list[str], args: argparse.Namespace) -> bool:
    """A shared baseline is only needed when the run will actually execute mutants."""
    return bool(files) and not (args.scan or args.update_manifest or args.check_manifest)


def _prepare_directory_baseline(args: argparse.Namespace, files: list[str], cwd: str) -> float:
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


def _report_excluded(excluded: list[str]) -> None:
    """Print one line per file --exclude dropped from the walk (--verbose only)."""
    for path in excluded:
        print(f"Excluded: {path}")


def _collect_union_files(args: argparse.Namespace, roots: list[str]) -> list[str]:
    """The union's .py files across all roots: root order, deduped, raises
    NoFilesToProcessError if the whole union is empty (an individual empty
    root is silent, item 17)."""
    kept: list[str] = []
    excluded: list[str] = []
    for root in roots:
        result = _collect_py_files(root, args.exclude or (), args.prune_dirs)
        kept.extend(result.kept)
        excluded.extend(result.excluded)
    kept = _dedup_by_realpath(kept)
    if args.verbose:
        _report_excluded(excluded)
    if not kept:
        raise NoFilesToProcessError()
    return kept


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
                _run_on_file(args, py_file, _load_source(py_file), cwd, baseline_duration),
            )
        except SyntaxError as exc:
            _report_parse_error(py_file, exc)
            exit_code = max(exit_code, 2)
            parse_failures += 1
    if parse_failures:
        print(f"error: {parse_failures} files could not be parsed", file=sys.stderr)
    sys.exit(exit_code)


def _dispatch_batch(args: argparse.Namespace, roots: list[str]) -> None:
    """One or more resolved roots: one shared baseline, and one exit code — the
    worst per-file code across the batch (item 2)."""
    _run_files_and_exit(args, _collect_union_files(args, roots))


def _raise_if_target_excluded(args: argparse.Namespace) -> None:
    """Raise NoFilesToProcessError when the single-file target itself
    matches an --exclude pattern."""
    if not _is_excluded(args.file, args.exclude or ()):
        return
    if args.verbose:
        print(f"Excluded: {args.file}")
    raise NoFilesToProcessError()


def _check_test_contexts_file(args: argparse.Namespace) -> None:
    if args.test_contexts is not None and not os.path.isfile(args.test_contexts):
        print(
            f"error: --test-contexts file not found: {args.test_contexts}",
            file=sys.stderr,
        )
        sys.exit(2)


def _resolve_roots(args: argparse.Namespace) -> tuple[list[str], tuple[str, ...]]:
    """Positionals/globs, or uv workspace autodiscovery when none are given
    (issue #22 item 3). Autodiscovery also returns the real
    [tool.uv.workspace].exclude directories, so the shared collector skips
    them by path identity in every walk (item 10's second half) — not by
    re-encoding a literal directory path as a glob pattern, which a "*" in
    the directory's own name would misinterpret."""
    if args.files:
        return _expand_roots(args.files), ()
    return _discover_workspace_roots(), tuple(_workspace_exclude_dirs())


def _dispatch(args: argparse.Namespace) -> None:
    """Resolve positionals (or autodiscover a workspace), then route by
    arity (issue #22 item 2).

    A single resolved path that is a file runs the single-file path below,
    untouched; a single directory or two or more roots run as one batch.
    """
    roots, args.prune_dirs = _resolve_roots(args)
    if len(roots) > 1:
        _dispatch_batch(args, roots)
        return
    # Populates the args.file scratch field declared in _build_parser; the
    # single-file path below and _dispatch_batch's excluded-target check
    # both read it from here.
    args.file = roots[0]
    if os.path.isdir(args.file):
        _dispatch_batch(args, [args.file])
        return
    source = _load_source(args.file)  # a bad path must report itself, not "excluded"
    _raise_if_target_excluded(args)
    try:
        sys.exit(_run_on_file(args, args.file, source, os.getcwd()))
    except SyntaxError as exc:
        _report_parse_error(args.file, exc)
        sys.exit(2)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _check_coverage_flags(args)
    _validate_mutual_exclusions(args)
    _check_test_contexts_file(args)
    try:
        _dispatch(args)
    except TargetResolutionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(exc.exit_code)


if __name__ == "__main__":
    main()
