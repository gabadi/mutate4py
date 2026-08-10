"""Unit tests for _cmd.run_argv (shared argv runner, no shell)."""

from mutate4py._cmd import run_argv


def test_run_argv_exit_zero_is_survived():
    assert run_argv(["true"], "/tmp", timeout=5.0) == "survived"


def test_run_argv_exit_nonzero_is_killed():
    assert run_argv(["false"], "/tmp", timeout=5.0) == "killed"


def test_run_argv_timeout_is_timeout():
    assert run_argv(["sleep", "10"], "/tmp", timeout=0.1) == "timeout"


def test_run_argv_uses_cwd(tmp_path):
    """cwd is actually used: command that lists a sentinel file only present in tmp_path."""
    sentinel = tmp_path / "sentinel_file.txt"
    sentinel.write_text("present")
    status = run_argv(["test", "-f", "sentinel_file.txt"], str(tmp_path), timeout=5.0)
    assert status == "survived", "Command should find the sentinel in cwd"
    status2 = run_argv(["test", "-f", "sentinel_file.txt"], "/tmp", timeout=5.0)
    assert status2 == "killed", "Command should NOT find the sentinel outside cwd"


def test_run_argv_capture_output_does_not_leak(capsys):
    """stdout/stderr from the command should not appear in the test output."""
    run_argv(["echo", "SHOULD_NOT_APPEAR"], "/tmp", timeout=5.0)
    captured = capsys.readouterr()
    assert "SHOULD_NOT_APPEAR" not in captured.out
    assert "SHOULD_NOT_APPEAR" not in captured.err


def test_run_argv_unresolvable_program_is_killed():
    """No shell means a missing argv[0] raises OSError instead of a shell's
    graceful nonzero exit; run_argv must still classify it, not crash."""
    assert run_argv(["no-such-program-xyz"], "/tmp", timeout=5.0) == "killed"
