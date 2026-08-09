"""CLI entry point for mutate4py."""

import argparse
import os
import sys

from mutate4py._dispatch import _dispatch
from mutate4py._target_resolution import TargetResolutionError

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


def _check_test_contexts_file(args: argparse.Namespace) -> None:
    if args.test_contexts is not None and not os.path.isfile(args.test_contexts):
        print(
            f"error: --test-contexts file not found: {args.test_contexts}",
            file=sys.stderr,
        )
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
