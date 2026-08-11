"""Unit tests for _subprocess_executor.SubprocessExecutor."""

import sys
import textwrap

from mutate4py._subprocess_executor import SubprocessExecutor


def _write_project(tmp_path, *, target_body: str, test_body: str) -> str:
    (tmp_path / "conftest.py").write_text("")
    (tmp_path / "under_test.py").write_text(textwrap.dedent(target_body))
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_under_test.py").write_text(textwrap.dedent(test_body))
    return str(tmp_path)


_ADD_TEST_BODY = "from under_test import add\ndef test_add():\n    assert add(2, 2) == 4\n"


def test_prime_is_a_noop():
    SubprocessExecutor(cwd="/tmp").prime()  # must not raise


def test_run_survives_when_tests_pass(tmp_path):
    cwd = _write_project(tmp_path, target_body="def add(a, b):\n    return a + b\n", test_body=_ADD_TEST_BODY)
    executor = SubprocessExecutor(cwd=cwd)
    assert executor.run(["-q", "tests"], timeout=30.0) == "survived"


def test_run_killed_when_tests_fail(tmp_path):
    cwd = _write_project(tmp_path, target_body="def add(a, b):\n    return a - b\n", test_body=_ADD_TEST_BODY)
    executor = SubprocessExecutor(cwd=cwd)
    assert executor.run(["-q", "tests"], timeout=30.0) == "killed"


def test_run_reports_no_tests_collected_when_filter_deselects_everything(tmp_path):
    """A -k filter matching nothing is pytest exit 5 ("no tests were
    collected") — must not be scored killed (issue #55)."""
    cwd = _write_project(tmp_path, target_body="def add(a, b):\n    return a + b\n", test_body=_ADD_TEST_BODY)
    executor = SubprocessExecutor(cwd=cwd)
    assert executor.run(["-q", "tests", "-k", "no_such_test_name"], timeout=30.0) == "no-tests-collected"


def test_run_reports_usage_error_for_a_stale_node_id(tmp_path):
    """A stale/renamed node ID (e.g. from a stale test-context db) is pytest
    exit 4 ("not found: ... no tests ran"), not exit 5 — must not be scored
    killed either (issue #55)."""
    cwd = _write_project(tmp_path, target_body="def add(a, b):\n    return a + b\n", test_body=_ADD_TEST_BODY)
    executor = SubprocessExecutor(cwd=cwd)
    status = executor.run(["-q", "tests/test_under_test.py::test_does_not_exist"], timeout=30.0)
    assert status == "usage-error"


def test_run_reports_timeout(tmp_path):
    cwd = _write_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body="import time\ndef test_slow():\n    time.sleep(5)\n",
    )
    executor = SubprocessExecutor(cwd=cwd)
    assert executor.run(["-q", "tests"], timeout=0.5) == "timeout"


def test_run_invokes_sys_executable_module_pytest(tmp_path, monkeypatch):
    """Regression: the subprocess executor must run `sys.executable -m
    pytest`, not a PATH-resolved `pytest`, so it never resolves to a
    different pytest than the forking executor's in-process import."""
    captured_argv = {}

    def fake_run_argv(argv, cwd, timeout):
        captured_argv["argv"] = argv
        captured_argv["cwd"] = cwd
        captured_argv["timeout"] = timeout
        return "survived"

    monkeypatch.setattr("mutate4py._subprocess_executor.run_argv", fake_run_argv)
    executor = SubprocessExecutor(cwd=str(tmp_path))
    status = executor.run(["-x", "-k", "foo"], timeout=12.0)

    assert status == "survived"
    assert captured_argv["argv"] == [sys.executable, "-m", "pytest", "-x", "-k", "foo"]
    assert captured_argv["cwd"] == str(tmp_path)
    assert captured_argv["timeout"] == 12.0


def test_run_does_not_leak_child_output(tmp_path, capsys):
    cwd = _write_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=(
            "from under_test import add\ndef test_add():\n    print('SHOULD_NOT_APPEAR')\n    assert add(2, 2) == 4\n"
        ),
    )
    executor = SubprocessExecutor(cwd=cwd)
    executor.run(["-q", "tests"], timeout=30.0)
    captured = capsys.readouterr()
    assert "SHOULD_NOT_APPEAR" not in captured.out
    assert "SHOULD_NOT_APPEAR" not in captured.err
