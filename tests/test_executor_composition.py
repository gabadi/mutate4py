"""Seam (b), the Executor interface, for a serial forking run: the executor
`select_executor` prepares is primed in a fork server, one Worker-server
process over the project tree itself under the Project environment, so the
orchestrator never forks a Mutant and its own imports never reach a child.
Real fork server, real pytest, no fakes.
"""

import importlib.util
import io
import os
import shutil
import sys
import types
from contextlib import redirect_stdout

import pytest

from mutate4py._discovery import discover_sites
from mutate4py._executor import ExecutorDescription
from mutate4py._executor_selection import select_executor
from mutate4py._runner import RunMutationsRequest, run_mutations

from ._measurement_helpers import measurement_for


def _write_calc_project(root, body="    return a + b\n") -> str:
    (root / "conftest.py").write_text("")
    target = root / "calc.py"
    target.write_text("def add(a, b):\n" + body)
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_calc.py").write_text("from calc import add\ndef test_add():\n    assert add(2, 2) == 4\n")
    return str(target)


# This repo's own environment has tach installed, a fork-unsafe plugin: a run
# that does not block it gets the subprocess executor (tested below).
_ARGS = ["-p", "no:tach", "-q", "tests"]


def _serial_executor(cwd, target, pytest_args=tuple(_ARGS), no_fork_reason=None):
    return select_executor(
        use_parallel=False,
        no_fork_reason=no_fork_reason,
        cwd=str(cwd),
        guarded_path=target,
        pytest_args=list(pytest_args),
    )


def _close(executor) -> None:
    close = getattr(executor, "close", None)
    if close is not None:
        close()


@pytest.mark.component
def test_a_target_the_orchestrator_imported_still_forks_from_the_fork_server(tmp_path, monkeypatch):
    target = _write_calc_project(tmp_path)
    leaked = types.ModuleType("calc")
    leaked.__file__ = target
    monkeypatch.setitem(sys.modules, "calc", leaked)

    executor = _serial_executor(tmp_path, target)
    try:
        assert executor.run(_ARGS, timeout=30.0) == "survived"
        (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n")
        assert executor.run(_ARGS, timeout=30.0) == "killed"
        assert executor.describe() == ExecutorDescription(mode="forking", fresh_import=2)
    finally:
        _close(executor)


@pytest.mark.component
def test_a_hanging_mutant_times_out_and_the_fork_server_keeps_serving(tmp_path):
    target = _write_calc_project(tmp_path, body="    while True:\n        pass\n")
    executor = _serial_executor(tmp_path, target)
    try:
        assert executor.run(_ARGS, timeout=1.0) == "timeout"
        (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n")
        assert executor.run(_ARGS, timeout=30.0) == "survived"
    finally:
        _close(executor)


@pytest.mark.component
def test_forking_and_subprocess_executors_classify_the_same_mutant_identically(tmp_path, monkeypatch):
    target = _write_calc_project(tmp_path)
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    forking = _serial_executor(tmp_path, target)
    plain = _serial_executor(tmp_path, target, no_fork_reason="--no-fork")
    try:
        assert [forking.run(_ARGS, 30.0), plain.run(_ARGS, 30.0)] == ["survived"] * 2
        (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n")
        assert [forking.run(_ARGS, 30.0), plain.run(_ARGS, 30.0)] == ["killed"] * 2
    finally:
        _close(forking)


# --- whole-run fallbacks still give the subprocess executor and say why ------


@pytest.mark.component
def test_no_fork_gives_the_subprocess_executor(tmp_path):
    target = _write_calc_project(tmp_path)
    executor = _serial_executor(tmp_path, target, no_fork_reason="--no-fork")
    assert executor.describe().render() == "subprocess (--no-fork)"


@pytest.mark.component
def test_a_platform_without_fork_gives_the_subprocess_executor(tmp_path, monkeypatch):
    import mutate4py._forking_executor as forking_mod

    monkeypatch.setattr(forking_mod, "is_available", lambda: False)
    target = _write_calc_project(tmp_path)
    executor = _serial_executor(tmp_path, target)
    assert executor.describe().render() == "subprocess (the forking executor needs a POSIX platform)"


@pytest.mark.component
def test_pytest_not_importable_in_the_fork_server_gives_the_subprocess_executor(tmp_path, monkeypatch):
    shadow = tmp_path / "shadow"
    (shadow / "pytest").mkdir(parents=True)
    (shadow / "pytest" / "__init__.py").write_text("raise ImportError('shadowed for this test')\n")
    project = tmp_path / "project"
    project.mkdir()
    target = _write_calc_project(project)
    monkeypatch.setenv("PYTHONPATH", str(shadow))

    executor = _serial_executor(project, target)
    try:
        assert executor.describe().render() == (
            "subprocess (forking executor unavailable: pytest is not importable in this process: "
            "shadowed for this test)"
        )
    finally:
        _close(executor)


@pytest.mark.component
def test_a_target_the_conftest_imports_at_prime_runs_each_mutant_in_a_fresh_interpreter(tmp_path, monkeypatch):
    target = _write_calc_project(tmp_path)
    (tmp_path / "conftest.py").write_text("import calc\n")
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    executor = _serial_executor(tmp_path, target)
    try:
        assert executor.run(_ARGS, timeout=30.0) == "survived"
        (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n")
        assert executor.run(_ARGS, timeout=30.0) == "killed"
        assert executor.describe().render() == "forking (fresh import 0, swap 0, fresh interpreter 2)"
    finally:
        _close(executor)


@pytest.mark.component
def test_a_hanging_mutant_in_a_fresh_interpreter_times_out_and_the_fork_server_keeps_serving(tmp_path):
    target = _write_calc_project(tmp_path, body="    while True:\n        pass\n")
    (tmp_path / "conftest.py").write_text("import calc\n")
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    executor = _serial_executor(tmp_path, target)
    try:
        (tmp_path / "calc.py").write_text("def add(a, b):\n    while True:\n        pass\n")
        assert executor.run(_ARGS, timeout=2.0) == "timeout"
        (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n")
        assert executor.run(_ARGS, timeout=30.0) == "survived"
    finally:
        _close(executor)


_SRC_PACKAGE = os.path.join(os.path.dirname(__file__), "..", "src", "mutate4py")

# Asserts the harness's own pytest runner reports a failing session as a failure.
_HARNESS_TEST = """\
import pytest

from mutate4py._forking_executor import _run_pytest_output_suppressed


def test_a_usage_error_is_reported_as_a_failure(tmp_path):
    assert _run_pytest_output_suppressed(pytest, ["--not-a-real-flag-xyz"], str(tmp_path)) != 0
"""

_EXIT_STATUS_LINE = "        return int(pytest_module.main(args, plugins=list(plugins)))\n"


def _write_harness_project(root) -> str:
    """A project holding its own copy of mutate4py, so the fork server, started in
    it, runs that copy: the guarded file is one of the fork server's own modules."""
    shutil.copytree(_SRC_PACKAGE, root / "mutate4py", ignore=shutil.ignore_patterns("__pycache__", "*.manifest.json"))
    (root / "conftest.py").write_text("")
    (root / "tests").mkdir()
    (root / "tests" / "test_harness.py").write_text(_HARNESS_TEST)
    return str(root / "mutate4py" / "_forking_executor.py")


@pytest.mark.component
def test_a_target_that_is_a_fork_server_module_runs_each_mutant_in_a_fresh_interpreter(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    target = _write_harness_project(tmp_path)
    clean = open(target).read()
    assert _EXIT_STATUS_LINE in clean
    executor = _serial_executor(tmp_path, target)
    try:
        assert executor.run(_ARGS, timeout=60.0) == "survived"
        # Swapped into the child's own harness, this Mutant would report every
        # pytest session as a pass, its own included: a false Survivor.
        mutant = clean.replace(
            _EXIT_STATUS_LINE, "        return 0 * int(pytest_module.main(args, plugins=list(plugins)))\n"
        )
        open(target, "w").write(mutant)
        assert executor.run(_ARGS, timeout=60.0) == "killed"
        assert executor.describe().render() == "forking (fresh import 0, swap 0, fresh interpreter 2)"
    finally:
        _close(executor)


@pytest.mark.component
@pytest.mark.skipif(importlib.util.find_spec("tach") is None, reason="needs tach, a fork-unsafe plugin, installed")
def test_a_fork_unsafe_plugin_in_the_run_gives_the_subprocess_executor_and_says_why(tmp_path):
    target = _write_calc_project(tmp_path)
    executor = _serial_executor(tmp_path, target, pytest_args=["-q", "tests"])
    try:
        assert executor.describe().render() == "subprocess (fork-unsafe plugin: tach.pytest_plugin)"
    finally:
        _close(executor)


def _write_marking_plugin(root) -> "os.PathLike":
    """A conftest-registered plugin that leaves a marker file when it is imported."""
    marker = root / "plugin-loaded"
    (root / "marking_plugin.py").write_text(f"open({str(marker)!r}, 'w').close()\n")
    (root / "conftest.py").write_text("pytest_plugins = ['marking_plugin']\n")
    return marker


@pytest.mark.component
@pytest.mark.parametrize(("pytest_args", "loaded"), [(["-p", "no:marking_plugin", *_ARGS], False), (_ARGS, True)])
def test_the_fork_server_primes_without_a_plugin_the_run_disables(tmp_path, pytest_args, loaded):
    target = _write_calc_project(tmp_path)
    marker = _write_marking_plugin(tmp_path)

    executor = _serial_executor(tmp_path, target, pytest_args=pytest_args)
    try:
        assert marker.exists() is loaded
    finally:
        _close(executor)


def _make_functions_source(n: int) -> str:
    return "".join(f"def f{i}(a, b):\n    return a + b\n\n" for i in range(1, n + 1))


def _write_per_function_project(root, n: int) -> str:
    (root / "conftest.py").write_text("")
    src = _make_functions_source(n)
    (root / "calc.py").write_text(src)
    tests_dir = root / "tests"
    tests_dir.mkdir()
    lines = ["from calc import " + ", ".join(f"f{i}" for i in range(1, n + 1))]
    for i in range(1, n + 1):
        lines += [f"def test_f{i}():", f"    assert f{i}(2, 2) == 4"]
    (tests_dir / "test_calc.py").write_text("\n".join(lines) + "\n")
    return src


def _run_serial(root, src: str, monkeypatch, pytest_args=tuple(_ARGS)) -> tuple[int, str]:
    """run_mutations over calc.py, serially, each Site narrowed to its own test."""
    src_path = str(root / "calc.py")
    sites = discover_sites(src)
    contexts = {f"tests/test_calc.py::test_f{i}": [s.line] for i, s in enumerate(sites, 1)}
    # A same-length Mutant written in the second the clean file compiled could load the stale .pyc.
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                pytest_args=list(pytest_args),
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                cwd=str(root),
                measurement=measurement_for(os.path.abspath(src_path), contexts),
            )
        )
    return rc, buf.getvalue()


@pytest.mark.component
def test_a_serial_run_narrows_each_mutant_and_forks_every_one_from_the_fork_server(tmp_path, monkeypatch):
    src = _write_per_function_project(tmp_path, 3)
    rc, output = _run_serial(tmp_path, src, monkeypatch)
    assert rc == 0, output
    assert "Test selection: narrowed 3, static 0" in output
    assert "Executor: forking (fresh import 3, swap 0, fresh interpreter 0)" in output
    assert _live_children() == [], "the run must close its fork server"


def _live_children() -> list[str]:
    import subprocess

    listed = subprocess.run(["pgrep", "-P", str(os.getpid())], capture_output=True, text=True)
    return listed.stdout.split()
