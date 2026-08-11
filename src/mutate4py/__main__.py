"""CLI entry point for mutate4py."""

import argparse
import logging
import sys

from mutate4py._cli_validation import (
    ValidationError,
    _check_coverage_flags,
    _check_test_contexts_file,
    _validate_mutual_exclusions,
)
from mutate4py._dispatch import _dispatch
from mutate4py._target_resolution import TargetResolutionError

DEFAULT_WARNING_THRESHOLD = 50

# Hardcoded rather than __name__: `python -m mutate4py` runs this file with
# __name__ == "__main__" (a top-level logger with no parent), while the
# installed console-script entry point imports it normally as
# "mutate4py.__main__". Hardcoding keeps this logger a child of the
# "mutate4py" logger that the package's __init__.py configures on import
# (which always runs first, under either entry point).
_logger = logging.getLogger("mutate4py.__main__")


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
        "--pytest-args",
        dest="pytest_args",
        default=None,
        metavar="ARGS",
        help="Extra arguments to pass to pytest, as one shell-quoted string "
        "(e.g. --pytest-args '-x -k foo'); pytest is the only supported "
        "runner and is invoked directly, never through a shell",
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
        help="Report additional detail, e.g. which files --exclude skipped",
    )
    parser.add_argument(
        "--test-contexts",
        dest="test_contexts",
        default=None,
        help="Path to a .coverage SQLite db (pytest --cov-context=test); enables per-mutant test selection",
    )
    parser.add_argument(
        "--build-test-contexts",
        dest="build_test_contexts",
        default=None,
        metavar="OUTPUT_PATH",
        help="Build a test-context db and write it to OUTPUT_PATH: one "
        "isolated coverage.py session per test pytest would collect (scoped "
        "by --pytest-args), then combined (see --test-contexts); no "
        "mutation run occurs, and no positional PATH target is accepted",
    )
    parser.add_argument(
        "--no-fork",
        action="store_true",
        dest="no_fork",
        help="Force the subprocess executor, skipping the forking executor "
        "fast path (on by default for serial runs on a POSIX platform; it "
        "falls back to a fresh subprocess per mutant automatically wherever "
        "it isn't safe or applicable, so this is only needed to force the "
        "old behavior, e.g. for debugging)",
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


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        _check_coverage_flags(args)
        _validate_mutual_exclusions(args)
        _check_test_contexts_file(args)
        _dispatch(args)
    except (ValidationError, TargetResolutionError) as exc:
        _logger.error(f"error: {exc}")
        sys.exit(exc.exit_code)


if __name__ == "__main__":
    main()
