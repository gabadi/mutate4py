"""CLI flag validation: illegal-combination checks that run before dispatch.

Each check raises `ValidationError` rather than exiting directly (mirrors
`TargetResolutionError`'s shape) so `main()` can catch it alongside target
resolution failures with a single except clause; the adapter owns the exit.
"""

import argparse
import glob
import os
import sys


class ValidationError(Exception):
    """Base for CLI flag-validation failures; carries the message and the
    process exit code the CLI adapter should use."""

    def __init__(self, message: str, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


# The flags removed in 0.3.0 (ADR 0008, 0021, 0022 superseded; spec #89): the run
# measures coverage itself and re-scores only what changed, so each is refused rather
# than silently ignored. The reason is the tail of the refusal message.
_REMOVED_FLAGS = (
    ("--cov-cmd", "cov_cmd", "the run measures coverage itself"),
    ("--lcov", "lcov", "the run measures coverage itself"),
    ("--reuse-coverage", "reuse_coverage", "the run measures coverage itself"),
    ("--test-contexts", "test_contexts", "the run measures coverage itself"),
    ("--build-test-contexts", "build_test_contexts", "the run measures coverage itself"),
    ("--since-last-run", "since_last_run", "a default run already re-scores only changed functions"),
    ("--lines", "lines", "re-score a function by editing it, or use --mutate-all"),
)


def _check_removed_flags(args: argparse.Namespace) -> None:
    """Raise, naming the flag, for the first flag removed in 0.3.0 that is set."""
    for flag, dest, reason in _REMOVED_FLAGS:
        value = getattr(args, dest)
        if value is None or value is False:
            continue
        raise ValidationError(f"{flag} removed in 0.3.0: {reason}")


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
    if args.mutate_all:
        _exit_incompatible(flag, "--mutate-all")
    if args.max_workers is not None:
        _exit_incompatible(flag, "--max-workers")


def _check_no_run_survivor_flag(args: argparse.Namespace) -> None:
    """Raise if --allow-survivors (a scored-run exit-code flag) is paired with a no-run mode."""
    if args.allow_survivors:
        _exit_incompatible(_no_run_flag(args), "--allow-survivors")


def _check_scan_only_incompatibilities(args: argparse.Namespace) -> None:
    """Raise if scan-only flags are paired with non-scan flags."""
    if args.timeout_factor != 10:
        _exit_incompatible("--scan", "--timeout-factor")
    if args.min_timeout != 5.0:
        _exit_incompatible("--scan", "--min-timeout")
    if args.pytest_args:
        _exit_incompatible("--scan", "--pytest-args")


def _check_no_run_mode_specific_incompatibilities(args: argparse.Namespace) -> None:
    """Raise the extra checks specific to whichever no-run mode is active."""
    if args.scan:
        _check_scan_only_incompatibilities(args)


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
        _check_no_run_survivor_flag(args)
        _check_no_run_mode_specific_incompatibilities(args)


def _nearest_project_root(target: str, cwd: str) -> str:
    """Nearest ancestor of `target` (itself included) holding a pyproject.toml,
    else cwd. A relative target resolves against cwd."""
    cwd = os.path.abspath(cwd)
    current = os.path.abspath(os.path.join(cwd, target))
    while True:
        if os.path.isfile(os.path.join(current, "pyproject.toml")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return cwd
        current = parent


def _env_mismatch_message(running: str, env: str) -> str:
    return (
        f"mutate4py is running under {running}, not the project environment {env}. "
        "From the project root, run `uv run --with mutate4py mutate4py <same arguments>`, "
        f"or `{env}/bin/python -m mutate4py <same arguments>` if mutate4py is installed there, "
        "so tests use the project's own dependencies."
    )


def _site_packages_dirs(env: str) -> set[str]:
    """Real paths of the venv's site-packages for the running Python's major.minor."""
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    return {os.path.realpath(p) for p in glob.glob(os.path.join(env, "lib", version, "site-packages"))}


def _pythonpath_entries() -> set[str]:
    return {os.path.realpath(p) for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p}


def _running_identity(running_prefix: str | None, sys_path: list[str] | None) -> tuple[str, set[str]]:
    """Real paths of the running prefix and of the sys.path entries; both are
    injectable so tests can stand in for an overlay. The live sys.path drops
    PYTHONPATH entries, which are not site processing."""
    prefix = os.path.realpath(sys.prefix if running_prefix is None else running_prefix)
    if sys_path is not None:
        return prefix, {os.path.realpath(p) for p in sys_path}
    return prefix, {os.path.realpath(p) for p in sys.path} - _pythonpath_entries()


def _is_running_env(env: str, running: str, path_entries: set[str]) -> bool:
    """True when `env` is the running environment: its prefix, or a `uv run --with`
    overlay whose sys.path holds the env's site-packages (ADR 0025)."""
    return running == os.path.realpath(env) or bool(path_entries & _site_packages_dirs(env))


def check_project_env(
    targets: list[str],
    cwd: str,
    running_prefix: str | None = None,
    sys_path: list[str] | None = None,
) -> None:
    """Reject a run whose project `.venv` is not the running environment
    (ADR 0025). The running environment is the interpreter's prefix, or a
    `uv run --with` overlay, whose prefix is temporary but which puts the
    project's site-packages on sys.path. With no `.venv/bin/python` there is
    nothing to compare, so no check. The cwd is always checked too, after the
    targets, because workspace autodiscovery resolves to it even when targets
    are given; no targets checks the cwd alone."""
    running, path_entries = _running_identity(running_prefix, sys_path)
    for target in dict.fromkeys([*targets, ""]):
        env = os.path.join(_nearest_project_root(target, cwd), ".venv")
        if not os.path.exists(os.path.join(env, "bin", "python")):
            continue
        if not _is_running_env(env, running, path_entries):
            raise ValidationError(_env_mismatch_message(running, env))


def check_run_env(
    args: argparse.Namespace,
    targets: list[str],
    cwd: str,
    running_prefix: str | None = None,
    sys_path: list[str] | None = None,
) -> None:
    """`check_project_env` for the modes that run the project's tests. The
    no-run modes (--scan, --update-manifest, --check-manifest) run no tests,
    so they are not held to the project environment."""
    if args.scan or args.update_manifest or args.check_manifest:
        return
    check_project_env(targets, cwd, running_prefix, sys_path)
