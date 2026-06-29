"""Unit tests for _cmd.run_command (shared subprocess helper)."""

from mutate4py._cmd import run_command


def test_run_command_exit_zero_is_survived():
    status, timed_out = run_command("exit 0", "/tmp", timeout=5.0)
    assert status == "survived"
    assert timed_out is False


def test_run_command_exit_nonzero_is_killed():
    status, timed_out = run_command("exit 1", "/tmp", timeout=5.0)
    assert status == "killed"
    assert timed_out is False


def test_run_command_timeout_is_timeout():
    status, timed_out = run_command("sleep 10", "/tmp", timeout=0.1)
    assert status == "timeout"
    assert timed_out is True


def test_run_command_uses_cwd(tmp_path):
    """cwd is actually used: command that lists a sentinel file only present in tmp_path."""
    sentinel = tmp_path / "sentinel_file.txt"
    sentinel.write_text("present")
    status, timed_out = run_command(
        "test -f sentinel_file.txt", str(tmp_path), timeout=5.0
    )
    assert status == "survived", "Command should find the sentinel in cwd"
    status2, _ = run_command("test -f sentinel_file.txt", "/tmp", timeout=5.0)
    assert status2 == "killed", "Command should NOT find the sentinel outside cwd"


def test_run_command_capture_output_does_not_leak(capsys):
    """stdout/stderr from the command should not appear in the test output."""
    run_command("echo SHOULD_NOT_APPEAR", "/tmp", timeout=5.0)
    captured = capsys.readouterr()
    assert "SHOULD_NOT_APPEAR" not in captured.out
    assert "SHOULD_NOT_APPEAR" not in captured.err
