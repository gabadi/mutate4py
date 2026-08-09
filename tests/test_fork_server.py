"""Unit/integration tests for _fork_server (issue #25 fork-server model)."""

import itertools
import os
import signal
import sys
import textwrap
import time
import types

import pytest

from mutate4py._fork_server import (
    ForkServer,
    ForkServerUnavailable,
    ModuleLeakError,
    assert_source_clean,
    is_available,
)
from mutate4py._fork_server import _wait_for_child

# --- is_available ----------------------------------------------------------


def test_is_available_true_for_plain_pytest():
    assert is_available("pytest") is True


def test_is_available_true_for_pytest_with_args():
    assert is_available("pytest -x -q") is True


def test_is_available_false_for_other_runner():
    assert is_available("tox -e py311") is False


def test_is_available_false_for_shell_pipeline():
    assert is_available("pytest && echo done") is False


def test_is_available_false_for_unclosed_quote():
    assert is_available("pytest 'unclosed") is False


def test_is_available_false_for_empty_command():
    assert is_available("") is False


def test_is_available_false_without_os_fork(monkeypatch):
    monkeypatch.delattr(os, "fork", raising=False)
    assert is_available("pytest") is False


# --- assert_source_clean / _leaked_modules ----------------------------------


def test_assert_source_clean_passes_when_target_not_imported(tmp_path):
    target = tmp_path / "not_imported.py"
    target.write_text("x = 1\n")
    assert_source_clean(str(target))


def test_assert_source_clean_raises_when_target_already_imported(tmp_path, monkeypatch):
    target = tmp_path / "leaked_target.py"
    target.write_text("x = 1\n")
    fake_module = types.ModuleType("leaked_target")
    fake_module.__file__ = str(target)
    monkeypatch.setitem(sys.modules, "leaked_target", fake_module)
    with pytest.raises(ModuleLeakError, match="leaked_target"):
        assert_source_clean(str(target))


def test_assert_source_clean_ignores_modules_without_file(monkeypatch, tmp_path):
    target = tmp_path / "no_file_module.py"
    target.write_text("x = 1\n")
    fake_module = types.ModuleType("builtin_like")
    monkeypatch.setitem(sys.modules, "builtin_like", fake_module)
    assert_source_clean(str(target))


def test_assert_source_clean_ignores_unrelated_modules(tmp_path):
    unrelated = tmp_path / "unrelated.py"
    unrelated.write_text("x = 1\n")
    target = tmp_path / "target.py"
    target.write_text("x = 1\n")
    # `os` itself is always in sys.modules; unrelated to target, must not trip.
    assert_source_clean(str(target))


# --- ForkServer.prime / run --------------------------------------------------


_module_name_counter = itertools.count()


def _write_fixture_project(tmp_path, *, target_body: str, test_body: str, conftest_body: str = "") -> tuple[str, str]:
    """Write a minimal pytest project; return (cwd, target_path).

    A root conftest.py (even empty) is what makes pytest add the project
    root to sys.path in prepend import mode — the standard flat-layout
    recipe real projects rely on, so the fixture must use it too.

    The target module's name is unique per call (not a fixed "under_test")
    so different tests in this file — all running in one shared outer
    pytest process — cannot collide with each other's sys.modules entries,
    which would otherwise mask exactly the leak this module exists to catch.
    """
    mod_name = f"under_test_{next(_module_name_counter)}"
    target = tmp_path / f"{mod_name}.py"
    target.write_text(textwrap.dedent(target_body).format(mod=mod_name))
    (tmp_path / "conftest.py").write_text(textwrap.dedent(conftest_body).format(mod=mod_name))
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / f"test_{mod_name}.py").write_text(textwrap.dedent(test_body).format(mod=mod_name))
    return str(tmp_path), str(target)


_ADD_TEST_BODY = "from {mod} import add\ndef test_add():\n    assert add(2, 2) == 4\n"


@pytest.mark.integration
def test_prime_succeeds_when_target_not_pre_imported(tmp_path):
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=_ADD_TEST_BODY,
    )
    server = ForkServer(cwd=cwd, extra_args=["-q", "tests"], guarded_path=target)
    server.prime()  # must not raise


@pytest.mark.integration
def test_prime_raises_module_leak_when_conftest_imports_target(tmp_path):
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=_ADD_TEST_BODY,
        conftest_body="import {mod}\n",
    )
    server = ForkServer(cwd=cwd, extra_args=["-q", "tests"], guarded_path=target)
    with pytest.raises(ModuleLeakError):
        server.prime()


@pytest.mark.integration
def test_prime_leak_does_not_poison_a_later_same_named_file(tmp_path):
    """Regression: a leaked module from one file's prime() must not survive
    to fool a *different* file's leak check later in the same process —
    exactly the shape of a directory batch run with colliding basenames."""
    dir_a = tmp_path / "a"
    dir_a.mkdir()
    cwd_a, target_a = _write_fixture_project(
        dir_a,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=_ADD_TEST_BODY,
        conftest_body="import {mod}\n",
    )
    server_a = ForkServer(cwd=cwd_a, extra_args=["-q", "tests"], guarded_path=target_a)
    with pytest.raises(ModuleLeakError):
        server_a.prime()

    # A second, unrelated file that happens to reuse the same module name.
    mod_name = os.path.splitext(os.path.basename(target_a))[0]
    dir_b = tmp_path / "b"
    dir_b.mkdir()
    target_b = dir_b / f"{mod_name}.py"
    target_b.write_text("def add(a, b):\n    return a + b\n")
    (dir_b / "conftest.py").write_text("")
    tests_b = dir_b / "tests"
    tests_b.mkdir()
    (tests_b / f"test_{mod_name}.py").write_text(_ADD_TEST_BODY.format(mod=mod_name))

    server_b = ForkServer(cwd=str(dir_b), extra_args=["-q", "tests"], guarded_path=str(target_b))
    server_b.prime()  # must not raise: file a's leak must not have persisted


@pytest.mark.integration
def test_run_survives_when_tests_pass(tmp_path):
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=_ADD_TEST_BODY,
    )
    server = ForkServer(cwd=cwd, extra_args=["-q", "tests"], guarded_path=target)
    server.prime()
    status, timed_out = server.run(timeout=30.0)
    assert status == "survived"
    assert timed_out is False


@pytest.mark.integration
def test_run_killed_when_tests_fail(tmp_path):
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a - b\n",  # mutated: - instead of +
        test_body=_ADD_TEST_BODY,
    )
    server = ForkServer(cwd=cwd, extra_args=["-q", "tests"], guarded_path=target)
    server.prime()
    status, timed_out = server.run(timeout=30.0)
    assert status == "killed"
    assert timed_out is False


@pytest.mark.integration
def test_run_picks_up_post_prime_mutation_from_disk(tmp_path):
    """The central correctness property: priming before the file is mutated
    must not leave a stale pre-mutation module cached for the child."""
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=_ADD_TEST_BODY,
    )
    server = ForkServer(cwd=cwd, extra_args=["-q", "tests"], guarded_path=target)
    server.prime()

    # First mutant: correct code, unmutated -> tests pass -> survived.
    status, _ = server.run(timeout=30.0)
    assert status == "survived"

    # Apply a mutation on disk, as _run_mutation_loop would between mutants.
    with open(target, "w") as f:
        f.write("def add(a, b):\n    return a - b\n")
    status, _ = server.run(timeout=30.0)
    assert status == "killed", (
        "child re-used a stale pre-mutation module instead of re-reading the file from disk after fork"
    )

    # Restore and re-run: must go back to survived, proving each fork reads
    # fresh rather than caching the previous child's result.
    with open(target, "w") as f:
        f.write("def add(a, b):\n    return a + b\n")
    status, _ = server.run(timeout=30.0)
    assert status == "survived"


@pytest.mark.integration
def test_run_reports_timeout_and_kills_child(tmp_path):
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=(
            "import time\nfrom {mod} import add\ndef test_add():\n    time.sleep(5)\n    assert add(2, 2) == 4\n"
        ),
    )
    server = ForkServer(cwd=cwd, extra_args=["-q", "tests"], guarded_path=target)
    server.prime()
    status, timed_out = server.run(timeout=0.5)
    assert status == "timeout"
    assert timed_out is True


@pytest.mark.integration
def test_run_before_prime_raises():
    server = ForkServer(cwd="/tmp", extra_args=["-q"], guarded_path="/tmp/x.py")
    with pytest.raises(ForkServerUnavailable):
        server.run(timeout=1.0)


@pytest.mark.integration
def test_run_does_not_leak_child_stdout(tmp_path, capsys):
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=(
            "from {mod} import add\ndef test_add():\n    print('SHOULD_NOT_APPEAR')\n    assert add(2, 2) == 4\n"
        ),
    )
    server = ForkServer(cwd=cwd, extra_args=["-q", "tests"], guarded_path=target)
    server.prime()
    server.run(timeout=30.0)
    captured = capsys.readouterr()
    assert "SHOULD_NOT_APPEAR" not in captured.out
    assert "SHOULD_NOT_APPEAR" not in captured.err


# --- _wait_for_child ---------------------------------------------------------


@pytest.mark.integration
def test_wait_for_child_reports_killed_when_child_dies_by_signal():
    """A child that dies from an external signal (not its own os._exit, e.g. a
    mutant that crashes the interpreter) must still resolve to "killed", not
    misread WEXITSTATUS on a status word that WIFSIGNALED, not WIFEXITED."""
    pid = os.fork()
    if pid == 0:
        time.sleep(5)
        os._exit(0)  # pragma: no cover - only reached if the signal below fails
    time.sleep(0.05)
    os.kill(pid, signal.SIGTERM)
    status, timed_out = _wait_for_child(pid, timeout=5.0)
    assert status == "killed"
    assert timed_out is False
