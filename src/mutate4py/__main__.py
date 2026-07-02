"""CLI entry point for mutate4py."""

import argparse
import os
import sys

from mutate4py._runner import (
    CoverageError,
    check_manifest,
    run_baseline,
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


def _collect_py_files(directory: str) -> list[str]:
    result = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for f in sorted(files):
            if f.endswith(".py"):
                result.append(os.path.join(root, f))
    return result


def _run_on_file(
    args: argparse.Namespace,
    py_file: str,
    source: str,
    cwd: str,
    baseline_duration: float | None = None,
) -> int:
    if args.check_manifest:
        return check_manifest(path=py_file, source=source)
    if args.update_manifest:
        update_manifest(path=py_file, source=source)
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


def _dispatch_directory(args: argparse.Namespace) -> None:
    files = _collect_py_files(args.file)
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


def _dispatch_single_file(args: argparse.Namespace, source: str, cwd: str) -> None:
    if args.check_manifest:
        sys.exit(check_manifest(path=args.file, source=source))
    if args.scan:
        _run_scan(args, source, cwd)
        return
    if args.update_manifest:
        update_manifest(path=args.file, source=source)
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
        )
    )


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _check_coverage_flags(args)
    _validate_mutual_exclusions(args)
    if args.test_contexts is not None and not os.path.isfile(args.test_contexts):
        print(
            f"error: --test-contexts file not found: {args.test_contexts}",
            file=sys.stderr,
        )
        sys.exit(2)
    if os.path.isdir(args.file):
        _dispatch_directory(args)
        return
    _dispatch_single_file(args, _load_source(args.file), os.getcwd())


if __name__ == "__main__":
    main()

# mutate4py-manifest-begin
# {"version":1,"tested_at":"2026-07-02T01:48:56Z","module_hash":"32777e82b0b3b4a9982ff5faa2919627d426bb07ceb1ce081394be0ae88ea3b5","functions":[{"id":"func/_positive_int","name":"_positive_int","line":19,"end_line":27,"hash":"06de4d3f74cf39cb40383657b49523cefc38cdf8566d5f8125553f3fd3c195d3"},{"id":"func/_build_parser","name":"_build_parser","line":30,"end_line":129,"hash":"672fb3d43c0aa60073f06287ace42d2e63d874447bb620bbff3d7e10771074fc"},{"id":"func/_check_coverage_flags","name":"_check_coverage_flags","line":132,"end_line":141,"hash":"42edc6617a1e291bd93d3578d7e32e708f713f9084ccba6be2331ad9b0ec9f87"},{"id":"func/_no_run_flag","name":"_no_run_flag","line":144,"end_line":150,"hash":"59aa486011c3e3158e11848b3f49b3182be927b8b3fc1c89b7b93890a7470ba9"},{"id":"func/_exit_incompatible","name":"_exit_incompatible","line":153,"end_line":155,"hash":"db2fe36913cbe87d3616570466315a8988310564ec93851dc7290d8065b8cee0"},{"id":"func/_check_no_run_incompatibilities","name":"_check_no_run_incompatibilities","line":158,"end_line":170,"hash":"53d50c7e588b2c2c608132917c7e016812ad25cb7f5f8fa6780e4a91ace9431b"},{"id":"func/_check_scan_only_incompatibilities","name":"_check_scan_only_incompatibilities","line":173,"end_line":180,"hash":"77d8a7f28df92300239bc3881b089c51438d9dafd77dd134a1e01964e4d24ada"},{"id":"func/_check_selection_exclusivity","name":"_check_selection_exclusivity","line":183,"end_line":194,"hash":"6ff1d994acd05c8dac1f9d7c4467a6fc74aa37899720361f85876e0f79a40e26"},{"id":"func/_validate_mutual_exclusions","name":"_validate_mutual_exclusions","line":197,"end_line":211,"hash":"6155e6243361768bcdfd18a457def365adbf180f8e41ac3f9e6497e59fe6790b"},{"id":"func/_load_source","name":"_load_source","line":214,"end_line":221,"hash":"b5c0322beb2e960c86d48fc3d00b8e1a910b64d4cfcadc414911fbcac6c7cc04"},{"id":"func/_parse_line_token","name":"_parse_line_token","line":224,"end_line":239,"hash":"3ede4fa8f423d5d27e97f3e7c6aec920c3e2e308159c05b42643d0c474b7fb86"},{"id":"func/_parse_lines","name":"_parse_lines","line":242,"end_line":247,"hash":"4febad296c3c5be36594a0188127548ab4edcba48a3bd946848e9c583b398ac4"},{"id":"func/_run_scan","name":"_run_scan","line":250,"end_line":264,"hash":"8075b51b362f0442df434fb5830df8d0de03eeb295e4bd0b1354700c6c9e29df"},{"id":"func/_collect_py_files","name":"_collect_py_files","line":267,"end_line":274,"hash":"3dd82fa868ce457a6024239044e42205bc3d9218355f35401fb058145e9f8150"},{"id":"func/_run_on_file","name":"_run_on_file","line":277,"end_line":323,"hash":"0c2e68f1e622a962ae8134453c57f1c4d0d25fb1d21330862043d938875ec7ce"},{"id":"func/_needs_directory_baseline","name":"_needs_directory_baseline","line":326,"end_line":330,"hash":"5d52f1c4f16dafb723d1963e0b2dc0e8aa625d0c3fe72a339d9c711bffe48a51"},{"id":"func/_prepare_directory_baseline","name":"_prepare_directory_baseline","line":333,"end_line":357,"hash":"811f2e34fd3d23c47aafd1c0e685a6ded294a940ea0873332b5411777396df3a"},{"id":"func/_dispatch_directory","name":"_dispatch_directory","line":360,"end_line":373,"hash":"1871680f3e0bde79b844ea330bc1980d42f273dd7c018ed3040479fdb3007dfc"},{"id":"func/_dispatch_single_file","name":"_dispatch_single_file","line":376,"end_line":405,"hash":"e20bf33a95e7a7ac5579f11bd2eebefa288d0ed88c066af8beacd93021d18ee7"},{"id":"func/main","name":"main","line":408,"end_line":422,"hash":"58fd6a6fdaf50ad3a0fa1c83943ad39ff9688067d63cdcc5ab0bd73ae2f341f7"}]}
# mutate4py-manifest-end
