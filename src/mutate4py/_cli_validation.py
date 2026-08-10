"""CLI flag validation: illegal-combination checks that run before dispatch.

Each check raises `ValidationError` rather than exiting directly (mirrors
`TargetResolutionError`'s shape) so `main()` can catch it alongside target
resolution failures with a single except clause; the adapter owns the exit.
"""

import argparse
import os


class ValidationError(Exception):
    """Base for CLI flag-validation failures; carries the message and the
    process exit code the CLI adapter should use."""

    def __init__(self, message: str, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _check_coverage_flags(args: argparse.Namespace) -> None:
    """Raise if more than one coverage flag is supplied (ADR 0008)."""
    cov_flags = [args.cov_cmd is not None, args.lcov is not None, args.reuse_coverage]
    if sum(cov_flags) > 1:
        raise ValidationError("--cov-cmd, --lcov, and --reuse-coverage are mutually exclusive; supply at most one.")


def _no_run_flag(args: argparse.Namespace) -> str:
    """Return the active no-run flag name for error messages."""
    if args.scan:
        return "--scan"
    if args.update_manifest:
        return "--update-manifest"
    return "--check-manifest"


def _exit_incompatible(flag_a: str, flag_b: str) -> None:
    raise ValidationError(f"{flag_a} cannot be combined with {flag_b}.")


def _check_no_run_incompatibilities(args: argparse.Namespace) -> None:
    """Raise if run-mode flags are paired with no-run-mode flags."""
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
    """Raise if scan-only flags are paired with non-scan flags."""
    if args.timeout_factor != 10:
        _exit_incompatible("--scan", "--timeout-factor")
    if args.min_timeout != 1.0:
        _exit_incompatible("--scan", "--min-timeout")
    if args.pytest_args:
        _exit_incompatible("--scan", "--pytest-args")


def _check_selection_exclusivity(args: argparse.Namespace) -> None:
    """Raise if more than one selection flag is set."""
    selection_count = sum([args.since_last_run, args.mutate_all, args.lines is not None])
    if selection_count > 1:
        raise ValidationError("--since-last-run, --mutate-all, and --lines are pairwise exclusive; supply at most one.")


def _validate_mutual_exclusions(args: argparse.Namespace) -> None:
    """Raise on illegal flag combinations (ADR 0008, 0014)."""
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
        raise ValidationError(f"--test-contexts file not found: {args.test_contexts}")
