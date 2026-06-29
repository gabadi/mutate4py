"""Testable helpers for cli_surface_steps.py."""

import shlex

_SCAN_INCOMPATIBLE_FLAGS = {"--timeout-factor", "--test-command", "--max-workers"}


def default_source() -> str:
    import textwrap

    return textwrap.dedent("""\
        def calc(a, b):
            return a > b
    """)


def lcov_content(src_path: str) -> str:
    return f"SF:{src_path}\nDA:2,1\nend_of_record\n"


def split_flags(flags_str: str) -> list[str]:
    """Split a flag string into a list, handling quoted values."""
    return shlex.split(flags_str)


def single_flag_args(flag_str: str, src: str, lcov: str) -> list[str]:
    """Return CLI args for a single-flag invocation."""
    if flag_str == "(none)":
        return [src, "--scan"]
    flags = split_flags(flag_str)
    flag_name = flags[0] if flags else ""
    if flag_name == "--test-command":
        return [src, "--lcov", lcov, "--test-command", "true"]
    if flag_name in _SCAN_INCOMPATIBLE_FLAGS:
        return [src, "--lcov", lcov, "--test-command", "true"] + flags
    return [src, "--scan"] + flags


def two_flag_args(flag1: str, flag2: str, src: str, lcov: str) -> list[str]:
    """Return CLI args for a two-flag invocation."""
    flags1 = split_flags(flag1) if flag1 != "(nothing)" else []
    flags2 = split_flags(flag2) if flag2 else []
    all_flags = flags1 + flags2
    flag_names = {f for f in all_flags if f.startswith("--")}
    if "--max-workers" in flag_names and not any(
        f in flag_names for f in ("--scan", "--update-manifest")
    ):
        return [src, "--lcov", lcov, "--test-command", "true"] + all_flags
    return [src] + all_flags


def accepted_flags_args(
    flags_str: str, src: str, lcov: str
) -> tuple[list[str], str, int | None]:
    """Return (cli_args, dispatch_target, dispatch_max_workers) for an accepted-flags invocation."""
    if flags_str == "--scan":
        return [src, "--scan"], "scan surface", None
    if flags_str == "--update-manifest":
        return [src, "--update-manifest"], "manifest write", None
    if flags_str == "(a coverage flag)":
        return [src, "--lcov", lcov, "--test-command", "true"], "run loop", None
    if flags_str == "--max-workers 4 (a coverage flag)":
        return (
            [src, "--lcov", lcov, "--max-workers", "4", "--test-command", "true"],
            "run loop",
            4,
        )
    raise NotImplementedError(f"Unknown flags: {flags_str!r}")


def assert_option_accepted(
    option: str, value: str, returncode: int, stderr: str
) -> None:
    """Assert that a CLI option was accepted (zero exit or no error in stderr)."""
    if option in ("mutation-warning", "timeout-factor", "test-command"):
        default_values = {
            "mutation-warning": "50",
            "timeout-factor": "10",
            "test-command": "pytest",
        }
        if value == default_values.get(option):
            assert returncode == 0 or "error" not in stderr.lower(), (
                f"Unexpected error with default {option}:\n{stderr}"
            )
        else:
            assert returncode == 0, (
                f"Expected accepted with --{option}={value}, got rc={returncode}\n{stderr}"
            )
    elif option == "max-workers":
        if value == "serial":
            assert returncode == 0 or "error" not in stderr.lower()
        else:
            assert returncode == 0, (
                f"Expected accepted with --max-workers={value}\n{stderr}"
            )


def described_args(description: str, src: str) -> list[str]:
    """Return CLI args for a descriptive invocation."""
    if description == "a valid file with --bogus-flag":
        return [src, "--bogus-flag"]
    if description == "no positional source file":
        return ["--scan"]
    if description == "a source path that does not exist":
        return ["/nonexistent/no_such_file.py", "--scan"]
    raise NotImplementedError(f"Unknown description: {description!r}")


def require_result(result) -> object:
    assert result is not None, "No CLI result captured"
    return result


def assert_accepted(returncode: int, stdout: str, stderr: str) -> None:
    assert returncode == 0, (
        f"Expected accepted (rc=0), got rc={returncode}\nstdout: {stdout}\nstderr: {stderr}"
    )


def assert_usage_error(returncode: int, stdout: str, stderr: str) -> None:
    assert returncode != 0, (
        f"Expected usage error (non-zero exit), got rc={returncode}\nstdout: {stdout}\nstderr: {stderr}"
    )


def assert_nonzero_exit(returncode: int) -> None:
    assert returncode != 0, f"Expected non-zero exit, got rc={returncode}"


def assert_zero_exit(returncode: int, stderr: str) -> None:
    assert returncode == 0, f"Expected exit 0, got rc={returncode}\n{stderr}"


def assert_no_analysis(stdout: str) -> None:
    assert "Mutation scan:" not in stdout
    assert "Mutation run:" not in stdout
    assert "Mutation Report" not in stdout


def assert_usage_printed(stdout: str) -> None:
    assert "usage:" in stdout.lower() or "mutate4py" in stdout, (
        f"Expected usage summary in stdout:\n{stdout}"
    )


def assert_usage_lists_max_workers(stdout: str) -> None:
    assert "--max-workers" in stdout, (
        f"Expected '--max-workers' in usage output:\n{stdout}"
    )


def assert_worker_count(
    dispatch_max_workers: int | None, count: str, returncode: int, stderr: str
) -> None:
    assert returncode == 0, (
        f"Expected accepted run with --max-workers {count}:\n{stderr}"
    )
    assert dispatch_max_workers == int(count), (
        f"Expected dispatch_max_workers={count}, got {dispatch_max_workers}"
    )


def assert_dispatched_to(
    target: str, returncode: int, stdout: str, stderr: str
) -> None:
    """Assert that the CLI dispatched to the expected behaviour."""
    if target == "scan surface":
        assert "Mutation scan:" in stdout, f"Expected scan output:\n{stdout}"
    elif target == "manifest write":
        assert "manifest" in stdout.lower(), f"Expected manifest output:\n{stdout}"
    elif target == "run loop":
        assert "Mutation run:" in stdout or returncode == 0, (
            f"Expected run loop output:\n{stdout}\nstderr: {stderr}"
        )
    else:
        raise NotImplementedError(f"Unknown target: {target!r}")
