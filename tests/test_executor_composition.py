"""Integration tests for issue 04a: narrowing (the run's Measurement) composing with
the warm forking executor in a single run — real ForkingExecutor, real Measurement
indexing, no fakes/stubs. Companion to the fake-executor unit tests in
test_run_mutations_modes.py, which cover the same dispatch logic without
paying for a real fork()/subprocess.
"""

import io
import os
import sys
import types
from contextlib import redirect_stdout

import pytest

from mutate4py._discovery import discover_sites
from mutate4py._forking_executor import ForkingExecutor
from mutate4py._runner import RunMutationsRequest, run_mutations

from ._measurement_helpers import measurement_for


def _make_functions_source(n: int) -> str:
    lines = []
    for i in range(1, n + 1):
        lines.append(f"def f{i}(a, b):")
        lines.append("    return a + b")
        lines.append("")
    return "\n".join(lines) + "\n"


def _measurement_per_function(src_path: str, sites) -> object:
    """A Measurement in which each Site's line is reached by its own test f<i>, so every Mutant narrows to one test."""
    lines_by_context = {f"tests/test_calc.py::test_f{i}": [s.line] for i, s in enumerate(sites, 1)}
    return measurement_for(os.path.abspath(src_path), lines_by_context)


def _write_per_function_pytest_project(cwd: str, n: int) -> None:
    tests_dir = os.path.join(cwd, "tests")
    os.makedirs(tests_dir, exist_ok=True)
    with open(os.path.join(cwd, "conftest.py"), "w") as f:
        f.write("")
    lines = ["from calc import " + ", ".join(f"f{i}" for i in range(1, n + 1))]
    for i in range(1, n + 1):
        lines.append(f"def test_f{i}():")
        lines.append(f"    assert f{i}(2, 2) == 4")
    with open(os.path.join(tests_dir, "test_calc.py"), "w") as f:
        f.write("\n".join(lines) + "\n")


# --- per-call args vary within one primed forking session ---------------------


@pytest.mark.component
def test_forking_executor_honors_different_args_within_one_primed_session(tmp_path):
    """The composition property this ticket is about: one primed session must
    run a *different* argv per run() call, not a fixed args list — otherwise
    per-site test-context narrowing could never reach the forking executor."""
    cwd = str(tmp_path)
    (tmp_path / "conftest.py").write_text("")
    target = tmp_path / "calc.py"
    target.write_text("def add(a, b):\n    return a + b\ndef sub(a, b):\n    return a - b\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_calc.py").write_text(
        "from calc import add, sub\n"
        "def test_add():\n    assert add(2, 2) == 4\n"
        "def test_sub_wrong():\n    assert sub(2, 2) == 1\n"  # always-failing on purpose
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=str(target))
    executor.prime()

    assert executor.run(["-q", "tests/test_calc.py::test_add"], timeout=30.0) == "survived"
    assert executor.run(["-q", "tests/test_calc.py::test_sub_wrong"], timeout=30.0) == "killed"
    assert executor.run(["-q", "tests/test_calc.py::test_add"], timeout=30.0) == "survived"


# --- real ForkingExecutor + the run's Measurement via run_mutations -----------


@pytest.mark.component
def test_forking_executor_composes_with_the_measurement_narrowing(tmp_path, monkeypatch):
    """End-to-end: run_mutations selects the forking executor (default,
    unguarded) and narrows each mutant's args per the run's Measurement."""
    import mutate4py._forking_executor as forking_mod

    created = []
    real_cls = forking_mod.ForkingExecutor

    class _TrackingForkingExecutor(real_cls):
        def __init__(self, *a, **kw):
            created.append(self)
            super().__init__(*a, **kw)

    monkeypatch.setattr(forking_mod, "ForkingExecutor", _TrackingForkingExecutor)

    cwd = str(tmp_path)
    src = _make_functions_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    _write_per_function_pytest_project(cwd, 3)

    sites = discover_sites(src)
    assert len(sites) == 3

    measurement = _measurement_per_function(src_path, sites)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                pytest_args=["-q", "tests"],
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                cwd=cwd,
                measurement=measurement,
            )
        )
    output = buf.getvalue()
    assert rc == 0
    assert "Test selection: narrowed 3, static 0" in output
    assert len(created) == 1, "expected the real forking executor to be instantiated exactly once"


# --- leaked-target degrades to subprocess, still classifies correctly ---------


@pytest.mark.component
def test_leaked_target_degrades_to_subprocess_and_still_narrows_correctly(tmp_path, monkeypatch):
    """A module-leak (forking ineligible for safety, not composition) must
    still fall back cleanly to the subprocess executor and preserve correct
    narrowed-dispatch classification — composition degrades, it doesn't break."""
    import mutate4py._subprocess_executor as subprocess_mod

    created = []
    real_cls = subprocess_mod.SubprocessExecutor

    class _TrackingSubprocessExecutor(real_cls):
        def __init__(self, *a, **kw):
            created.append(self)
            super().__init__(*a, **kw)

    monkeypatch.setattr(subprocess_mod, "SubprocessExecutor", _TrackingSubprocessExecutor)

    cwd = str(tmp_path)
    src = _make_functions_source(2)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    _write_per_function_pytest_project(cwd, 2)

    sites = discover_sites(src)

    measurement = _measurement_per_function(src_path, sites)

    fake_module = types.ModuleType("calc")
    fake_module.__file__ = src_path
    monkeypatch.setitem(sys.modules, "calc", fake_module)
    # Without this, a same-length mutant written in the same second as the
    # baseline compile can load the stale original .pyc and "survive" (flaky rc).
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                pytest_args=["-q", "tests"],
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                cwd=cwd,
                measurement=measurement,
            )
        )
    output = buf.getvalue()
    assert rc == 0
    assert "Test selection: narrowed 2, static 0" in output
    assert len(created) == 1, "expected the subprocess fallback to actually be used"


# --- executor parity: forking vs subprocess classify an identical mutant the same


@pytest.mark.component
def test_forking_and_subprocess_executors_classify_the_same_mutant_identically(tmp_path):
    from mutate4py._subprocess_executor import SubprocessExecutor

    cwd = str(tmp_path)
    (tmp_path / "conftest.py").write_text("")
    target = tmp_path / "calc.py"
    target.write_text("def add(a, b):\n    return a + b\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_calc.py").write_text("from calc import add\ndef test_add():\n    assert add(2, 2) == 4\n")
    args = ["-q", "tests"]

    forking = ForkingExecutor(cwd=cwd, guarded_path=str(target))
    forking.prime()
    subprocess_executor = SubprocessExecutor(cwd=cwd, guarded_path=str(target))
    subprocess_executor.prime()

    # Unmutated: both must report "survived".
    assert forking.run(args, timeout=30.0) == "survived"
    assert subprocess_executor.run(args, timeout=30.0) == "survived"

    # Mutated (+ -> -): both must report "killed".
    target.write_text("def add(a, b):\n    return a - b\n")
    assert forking.run(args, timeout=30.0) == "killed"
    assert subprocess_executor.run(args, timeout=30.0) == "killed"
