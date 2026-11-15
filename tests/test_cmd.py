"""Unit tests for _cmd.run_argv (shared argv runner, no shell)."""

import os
import subprocess

from mutate4py._cmd import classify_exit_code, run_argv
import pytest


def _stub_child(monkeypatch, *, returncode: int = 0, error: BaseException | None = None) -> None:
    """Answer the child-process boundary (subprocess.run) without starting a process: the child exits with
    `returncode`, or the run raises `error`."""

    def fake_run(argv, **kwargs):
        if error is not None:
            raise error
        return subprocess.CompletedProcess(argv, returncode)

    monkeypatch.setattr(subprocess, "run", fake_run)


@pytest.mark.unit
def test_run_argv_passes_env(monkeypatch):
    """env is the child's whole environment: a probe var present only there is seen (issue #81).

    The child is stubbed: it exits 0 only when PROBE is in the env handed to subprocess.run."""

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0 if kwargs["env"].get("PROBE") == "yes" else 1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    path_only = {"PATH": os.environ["PATH"]}
    probe = 'test "$PROBE" = yes'
    assert run_argv(["sh", "-c", probe], "/tmp", timeout=5.0, env={**path_only, "PROBE": "yes"}) == "survived"
    assert run_argv(["sh", "-c", probe], "/tmp", timeout=5.0, env=path_only) == "killed"


@pytest.mark.unit
def test_run_argv_exit_zero_is_survived(monkeypatch):
    _stub_child(monkeypatch, returncode=0)
    assert run_argv(["true"], "/tmp", timeout=5.0) == "survived"


@pytest.mark.unit
def test_run_argv_exit_nonzero_is_killed(monkeypatch):
    _stub_child(monkeypatch, returncode=1)
    assert run_argv(["false"], "/tmp", timeout=5.0) == "killed"


@pytest.mark.unit
def test_run_argv_exit_5_is_no_tests_collected(monkeypatch):
    """pytest exit 5 ("no tests were collected") must not be scored killed (issue #55)."""
    _stub_child(monkeypatch, returncode=5)
    assert run_argv(["sh", "-c", "exit 5"], "/tmp", timeout=5.0) == "no-tests-collected"


@pytest.mark.unit
def test_run_argv_exit_4_is_usage_error(monkeypatch):
    """pytest exit 4 (usage error) must not be scored killed either (issue #55)."""
    _stub_child(monkeypatch, returncode=4)
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
def test_run_argv_timeout_is_timeout(monkeypatch):
    _stub_child(monkeypatch, error=subprocess.TimeoutExpired(["sleep", "10"], 0.1))
    assert run_argv(["sleep", "10"], "/tmp", timeout=0.1) == "timeout"


@pytest.mark.system
def test_run_argv_uses_cwd(tmp_path):
    """cwd is actually used: command that lists a sentinel file only present in tmp_path."""
    sentinel = tmp_path / "sentinel_file.txt"
    sentinel.write_text("present")
    status = run_argv(["test", "-f", "sentinel_file.txt"], str(tmp_path), timeout=5.0)
    assert status == "survived", "Command should find the sentinel in cwd"
    status2 = run_argv(["test", "-f", "sentinel_file.txt"], "/tmp", timeout=5.0)
    assert status2 == "killed", "Command should NOT find the sentinel outside cwd"


@pytest.mark.system
def test_run_argv_capture_output_does_not_leak(capfd):
    """stdout/stderr from the command are captured by run_argv, not written to this process's fds.

    capfd, not capsys: the child writes straight to fd 1 and fd 2, which capsys (sys.stdout only) never sees.
    """
    run_argv(["sh", "-c", "echo SHOULD_NOT_APPEAR; echo SHOULD_NOT_APPEAR >&2"], "/tmp", timeout=5.0)
    captured = capfd.readouterr()
    assert "SHOULD_NOT_APPEAR" not in captured.out
    assert "SHOULD_NOT_APPEAR" not in captured.err


@pytest.mark.unit
def test_run_argv_unresolvable_program_is_killed(monkeypatch):
    """No shell means a missing argv[0] raises OSError instead of a shell's
    graceful nonzero exit; run_argv must still classify it, not crash."""
    _stub_child(monkeypatch, error=FileNotFoundError(2, "No such file or directory", "no-such-program-xyz"))
    assert run_argv(["no-such-program-xyz"], "/tmp", timeout=5.0) == "killed"
