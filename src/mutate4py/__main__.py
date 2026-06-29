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
    no_run = [("--scan", args.scan), ("--update-manifest", args.update_manifest), ("--check-manifest", args.check_manifest)]
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
            lines_filter=lines_filter,
            since_last_run=args.since_last_run,
            mutate_all=args.mutate_all,
            warning_threshold=args.warning_threshold,
            max_workers=max_workers,
            cwd=cwd,
        )
    )


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _check_coverage_flags(args)
    _validate_mutual_exclusions(args)
    if os.path.isdir(args.file):
        _dispatch_directory(args)
        return
    _dispatch_single_file(args, _load_source(args.file), os.getcwd())


if __name__ == "__main__":
    main()

# mutate4py-manifest-begin
# {"version":1,"tested_at":"2026-06-29T00:46:25Z","module_hash":"38633ea1aa63b9a53eda21f6d8cf551ad1014c4497362fc7084dc0575d1fa172","functions":[{"id":"func/_positive_int","name":"_positive_int","line":18,"end_line":26,"hash":"6cda3faf99bd40d84db75b661de5ed0d4a38764065d60d244997a74612345f80"},{"id":"func/_build_parser","name":"_build_parser","line":29,"end_line":115,"hash":"fbfdb74fec398bf80f2fefe5f060148234d8ba26d23eb488cb345751375bd9a9"},{"id":"func/_check_coverage_flags","name":"_check_coverage_flags","line":118,"end_line":127,"hash":"d6cc1826520d6233dea18144d198d0586a9a351500d4e062cb30bedd1adcae1c"},{"id":"func/_no_run_flag","name":"_no_run_flag","line":130,"end_line":136,"hash":"b1963ca7bc01c3ec166bc03315228f7d9a7015125e9f929b980436b2827780ae"},{"id":"func/_exit_incompatible","name":"_exit_incompatible","line":139,"end_line":141,"hash":"bc0a2b4f6e4c811d7bc93d65b7f8fee8b26d80048fe3daf59739365d8549a04b"},{"id":"func/_check_no_run_incompatibilities","name":"_check_no_run_incompatibilities","line":144,"end_line":154,"hash":"9cb398612c55edf940de66c84930879727d229f5d3aebe068b0d65f517d0a1b4"},{"id":"func/_check_scan_only_incompatibilities","name":"_check_scan_only_incompatibilities","line":157,"end_line":162,"hash":"3b1f2e91ebbcfc7048ed842622d4b02c85eab4e047ed1cca482eb037c70a971b"},{"id":"func/_check_selection_exclusivity","name":"_check_selection_exclusivity","line":165,"end_line":176,"hash":"0d71ec910056b5f5bd16840b1996df0650cb62a40bdbf96bae553e57368295b8"},{"id":"func/_validate_mutual_exclusions","name":"_validate_mutual_exclusions","line":179,"end_line":189,"hash":"64405cfa9070f1153a02431a853ce50bd2baef73e605411e0d7c163b21f77e81"},{"id":"func/_load_source","name":"_load_source","line":192,"end_line":199,"hash":"4b7ba929a21e045f6074d3a581200c7d30a00431442f4e1f176360dfb2bd5ba0"},{"id":"func/_parse_line_token","name":"_parse_line_token","line":202,"end_line":217,"hash":"3c54a507ecb1efcdbd91da6266e62dae6eec6fcda8fea81834cdcc84a4361d83"},{"id":"func/_parse_lines","name":"_parse_lines","line":220,"end_line":225,"hash":"a22047bfc6f665172728957e47bf58ae861f1134fd3ab8db9225c19ec7887140"},{"id":"func/_run_scan","name":"_run_scan","line":228,"end_line":242,"hash":"0515def26a76c19c345aaa4242150033bf4f6eb0480ca45b960dc159aaa97f71"},{"id":"func/_collect_py_files","name":"_collect_py_files","line":245,"end_line":252,"hash":"a293f244fd77df7df0584bd3b294ba5ae7dfaf4ba676dd76bb1ef09a0dc2287d"},{"id":"func/_run_on_file","name":"_run_on_file","line":255,"end_line":274,"hash":"bb6b7910e7a820bbbc169614e12671eaef89e0b44d141ee208a4431f0e3ce380"},{"id":"func/_dispatch_directory","name":"_dispatch_directory","line":277,"end_line":289,"hash":"b2d5ed32223dc1cea62ddfab781accf0cb0a10812cceba9e0158625b223f9da1"},{"id":"func/_dispatch_single_file","name":"_dispatch_single_file","line":292,"end_line":319,"hash":"03362d1692e4e652e3fbba33f03d3bc57909421f6d4514f97a9fb4bca65fc742"},{"id":"func/main","name":"main","line":322,"end_line":330,"hash":"8405d6a88ab6da1933c4b4f697eb551ee038ba147742f0c2cc15eb95125bf682"}]}
# mutate4py-manifest-end
