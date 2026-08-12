"""Unit tests for _cmd.run_argv (shared argv runner, no shell)."""

from mutate4py._cmd import classify_exit_code, run_argv
import pytest


@pytest.mark.unit
def test_run_argv_exit_zero_is_survived():
    assert run_argv(["true"], "/tmp", timeout=5.0) == "survived"


@pytest.mark.unit
def test_run_argv_exit_nonzero_is_killed():
    assert run_argv(["false"], "/tmp", timeout=5.0) == "killed"


@pytest.mark.unit
def test_run_argv_exit_5_is_no_tests_collected():
    """pytest exit 5 ("no tests were collected") must not be scored killed (issue #55)."""
    assert run_argv(["sh", "-c", "exit 5"], "/tmp", timeout=5.0) == "no-tests-collected"


@pytest.mark.unit
def test_run_argv_exit_4_is_usage_error():
    """pytest exit 4 (usage error) must not be scored killed either (issue #55)."""
    assert run_argv(["sh", "-c", "exit 4"], "/tmp", timeout=5.0) == "usage-error"


@pytest.mark.unit
def test_classify_exit_code_zero_is_survived():
    assert classify_exit_code(0) == "survived"


@pytest.mark.unit
def test_classify_exit_code_one_is_killed():
    assert classify_exit_code(1) == "killed"


@pytest.mark.unit
def test_classify_exit_code_five_is_no_tests_collected():
    assert classify_exit_code(5) == "no-tests-collected"


@pytest.mark.unit
def test_classify_exit_code_four_is_usage_error():
    assert classify_exit_code(4) == "usage-error"


@pytest.mark.unit
def test_run_argv_timeout_is_timeout():
    assert run_argv(["sleep", "10"], "/tmp", timeout=0.1) == "timeout"


@pytest.mark.unit
def test_run_argv_uses_cwd(tmp_path):
    """cwd is actually used: command that lists a sentinel file only present in tmp_path."""
    sentinel = tmp_path / "sentinel_file.txt"
    sentinel.write_text("present")
    status = run_argv(["test", "-f", "sentinel_file.txt"], str(tmp_path), timeout=5.0)
    assert status == "survived", "Command should find the sentinel in cwd"
    status2 = run_argv(["test", "-f", "sentinel_file.txt"], "/tmp", timeout=5.0)
    assert status2 == "killed", "Command should NOT find the sentinel outside cwd"


@pytest.mark.unit
def test_run_argv_capture_output_does_not_leak(capsys):
    """stdout/stderr from the command should not appear in the test output."""
    run_argv(["echo", "SHOULD_NOT_APPEAR"], "/tmp", timeout=5.0)
    captured = capsys.readouterr()
    assert "SHOULD_NOT_APPEAR" not in captured.out
    assert "SHOULD_NOT_APPEAR" not in captured.err


@pytest.mark.unit
def test_run_argv_unresolvable_program_is_killed():
    """No shell means a missing argv[0] raises OSError instead of a shell's
    graceful nonzero exit; run_argv must still classify it, not crash."""
    assert run_argv(["no-such-program-xyz"], "/tmp", timeout=5.0) == "killed"
