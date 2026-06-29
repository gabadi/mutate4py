"""CLI entry point for mutate4py."""

import argparse
import os
import sys

from mutate4py._runner import (
    CoverageError,
    check_manifest,
    run_mutations,
    run_scan,
    update_manifest,
)

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
    parser.add_argument("file", help="Python source file or directory to analyse")
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
        help="Mutant timeout = max(1s, factor × baseline duration) (default: 10)",
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


def _check_scan_only_incompatibilities(args: argparse.Namespace) -> None:
    """Exit if scan-only flags are paired with non-scan flags."""
    if args.timeout_factor != 10:
        _exit_incompatible("--scan", "--timeout-factor")
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
    if args.scan and args.update_manifest:
        _exit_incompatible("--scan", "--update-manifest")
    if args.scan and args.check_manifest:
        _exit_incompatible("--scan", "--check-manifest")
    if args.update_manifest and args.check_manifest:
        _exit_incompatible("--update-manifest", "--check-manifest")

    if args.scan or args.update_manifest or args.check_manifest:
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


def _collect_py_files(directory: str) -> list[str]:
    result = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for f in sorted(files):
            if f.endswith(".py"):
                result.append(os.path.join(root, f))
    return result


def _run_on_file(args: argparse.Namespace, py_file: str, source: str, cwd: str) -> int:
    if args.check_manifest:
        return check_manifest(path=py_file, source=source)
    if args.update_manifest:
        update_manifest(path=py_file, source=source)
        return 0
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


def _dispatch_directory(args: argparse.Namespace) -> None:
    if not (args.scan or args.update_manifest or args.check_manifest):
        print(
            "error: run mode requires a single file, not a directory.", file=sys.stderr
        )
        sys.exit(2)
    files = _collect_py_files(args.file)
    cwd = os.getcwd()
    exit_code = 0
    for py_file in files:
        if _run_on_file(args, py_file, _load_source(py_file), cwd) != 0:
            exit_code = 1
    sys.exit(exit_code)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _check_coverage_flags(args)
    _validate_mutual_exclusions(args)

    if os.path.isdir(args.file):
        _dispatch_directory(args)
        return

    source = _load_source(args.file)

    if args.check_manifest:
        sys.exit(check_manifest(path=args.file, source=source))
    elif args.scan:
        _run_scan(args, source, os.getcwd())
    elif args.update_manifest:
        update_manifest(path=args.file, source=source)
    else:
        lines_filter = _parse_lines(args.lines)
        max_workers = args.max_workers if args.max_workers is not None else 0
        exit_code = run_mutations(
            path=args.file,
            source=source,
            cov_cmd=args.cov_cmd,
            lcov_path=args.lcov,
            reuse_coverage=args.reuse_coverage,
            test_command=args.test_command,
            timeout_factor=args.timeout_factor,
            lines_filter=lines_filter,
            since_last_run=args.since_last_run,
            mutate_all=args.mutate_all,
            warning_threshold=args.warning_threshold,
            max_workers=max_workers,
            cwd=os.getcwd(),
        )
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
