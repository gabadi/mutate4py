"""Testable helpers for cli_surface_steps.py."""

import os
import shlex

_SCAN_INCOMPATIBLE_FLAGS = {"--timeout-factor", "--pytest-args", "--max-workers"}

_FAKE_PYTEST_ARGS = "-q tests"

_MANIFEST_REPORT_PREFIXES = (
    "Manifest missing:",
    "Manifest current:",
    "Manifest stale:",
)


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
    if flag_name == "--pytest-args":
        return [src, "--lcov", lcov, "--pytest-args", _FAKE_PYTEST_ARGS]
    if flag_name in _SCAN_INCOMPATIBLE_FLAGS:
        return [src, "--lcov", lcov, "--pytest-args", _FAKE_PYTEST_ARGS] + flags
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
        return [src, "--lcov", lcov, "--pytest-args", _FAKE_PYTEST_ARGS] + all_flags
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
        return [src, "--lcov", lcov, "--pytest-args", _FAKE_PYTEST_ARGS], "run loop", None
    if flags_str == "--max-workers 4 (a coverage flag)":
        return (
            [src, "--lcov", lcov, "--max-workers", "4", "--pytest-args", _FAKE_PYTEST_ARGS],
            "run loop",
            4,
        )
    raise NotImplementedError(f"Unknown flags: {flags_str!r}")


def assert_option_accepted(
    option: str, value: str, returncode: int, stderr: str
) -> None:
    """Assert that a CLI option was accepted (zero exit or no error in stderr)."""
    if option in ("mutation-warning", "timeout-factor", "pytest-args"):
        default_values = {
            "mutation-warning": "50",
            "timeout-factor": "10",
            "pytest-args": "(none)",
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
    if description == "a valid file with --test-command":
        return [src, "--test-command", "pytest"]
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


def source_file_run_args(flag_str: str, src: str) -> list[str]:
    """Return CLI args: the background source file plus a flag string."""
    return [src, *split_flags(flag_str)]


def overlapping_coverage_fixture_dir(repo_root: str) -> str:
    """Absolute path to the checked-in overlapping_coverage fixture."""
    return os.path.join(repo_root, "tests", "fixtures", "overlapping_coverage")


def build_test_contexts_fixture_args(db_path: str) -> list[str]:
    """Args for a --build-test-contexts run scoped to the checked-in
    overlapping_coverage fixture (two tests sharing one covered line).

    Must run with cwd=<fixture dir> (not the repo root): this project's own
    pyproject.toml restricts `[tool.coverage.run] source = ["mutate4py"]`,
    which — if honoured, as it would be were cwd the repo root — silently
    drops every file under tests/fixtures from coverage, leaving the built
    db's `file` table empty. Running from the fixture dir means coverage.py's
    config discovery finds the fixture's own unrestricted `.coveragerc`
    instead, and node IDs collect correctly relative to that same cwd.
    """
    return ["--build-test-contexts", db_path]


def assert_db_narrows_shared_line(db_path: str, fixture_dir: str) -> None:
    """Assert the built db narrows the fixture's shared line to both covering
    tests (the isolated-session build's whole point; see ADR 0021)."""
    from mutate4py._test_selection import TestContextDB

    shared_py = os.path.join(fixture_dir, "shared.py")
    db = TestContextDB(db_path)
    try:
        outcome, node_ids = db.tests_for_line(shared_py, 2)
        assert outcome == "narrowed", f"expected narrowed, got {outcome!r}"
        assert len(node_ids) == 2, f"expected both covering tests, got {node_ids}"
    finally:
        db.close()


def exclude_run_args(mode_flag: str, pattern: str, directory: str) -> list[str]:
    """Return CLI args for a directory-mode run under a single --exclude pattern."""
    return [directory] + split_flags(mode_flag) + ["--exclude", pattern]


def two_target_run_args(mode_flag: str, file1: str, file2: str) -> list[str]:
    """Return CLI args for a two-positional-target (union) invocation."""
    return [file1, file2] + split_flags(mode_flag)


def reported_manifest_files(stdout: str) -> list[str]:
    """Basenames of the files a --check-manifest run reported on, in output order."""
    names = []
    for line in stdout.splitlines():
        for prefix in _MANIFEST_REPORT_PREFIXES:
            if line.startswith(prefix):
                names.append(os.path.basename(line[len(prefix) :].strip()))
    return names


def assert_only_reported(stdout: str, expected: str) -> None:
    """Assert the run reported on exactly one file, and that it is `expected`."""
    reported = reported_manifest_files(stdout)
    assert reported == [expected], (
        f"Expected only {expected!r} to be reported, got {reported}:\n{stdout}"
    )


def assert_all_reported(stdout: str, expected: list[str]) -> None:
    """Assert the run reported on exactly this set of files (order-independent —
    a union batch's per-root order isn't what this scenario is pinning)."""
    reported = set(reported_manifest_files(stdout))
    assert reported == set(expected), (
        f"Expected {expected!r} to be reported, got {reported}:\n{stdout}"
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
