"""Integration tests for issue 04b: the Worker subprocess protocol
(`_worker_protocol.WorkerProcessExecutor` <-> `_worker_server.main`) — real
subprocesses, real pytest, no fakes. Companion to the fake-executor unit
tests in test_workers.py, which cover the same dispatch logic without paying
for a real subprocess spawn.
"""

import io
import json
import os
import sys
import types

import pytest

from mutate4py._worker_protocol import WorkerProcessExecutor


def _write_add_sub_project(tmp_path):
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
    return target


# --- WorkerProcessExecutor/_worker_server round trip --------------------------


@pytest.mark.component
def test_worker_process_executor_round_trip(tmp_path):
    """Formalizes the manual verification from the session that fixed the
    stdout-flush leak: one primed Worker subprocess serves multiple, distinct
    argv dispatches over the JSON-lines protocol without corrupting framing."""
    target = _write_add_sub_project(tmp_path)
    executor = WorkerProcessExecutor(worker_root=str(tmp_path), guarded_path=str(target), forking_requested=True)
    executor.prime()
    try:
        assert executor.run(["-q", "tests/test_calc.py::test_add"], timeout=30.0) == "survived"
        assert executor.run(["-q", "tests/test_calc.py::test_sub_wrong"], timeout=30.0) == "killed"
        assert executor.run(["-q", "tests/test_calc.py::test_add"], timeout=30.0) == "survived"
    finally:
        executor.close()


@pytest.mark.component
def test_worker_process_executor_subprocess_forced(tmp_path):
    """Same round trip with forking_requested=False: the Worker's own
    _prepare_executor call must fall back to the subprocess executor and
    still classify correctly."""
    target = _write_add_sub_project(tmp_path)
    executor = WorkerProcessExecutor(worker_root=str(tmp_path), guarded_path=str(target), forking_requested=False)
    executor.prime()
    try:
        assert executor.run(["-q", "tests/test_calc.py::test_add"], timeout=30.0) == "survived"
        assert executor.run(["-q", "tests/test_calc.py::test_sub_wrong"], timeout=30.0) == "killed"
    finally:
        executor.close()


# --- per-Worker identity reaches pytest-django's expected attribute (issue 05) -


def _write_workerinput_probe_project(tmp_path):
    (tmp_path / "conftest.py").write_text("")
    target = tmp_path / "calc.py"
    target.write_text("def add(a, b):\n    return a + b\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_worker_id.py").write_text(
        "from calc import add\n"
        "def test_workerinput_matches(request):\n"
        "    assert request.config.workerinput == {'workerid': 'gw3'}\n"
        "    assert add(2, 2) == 4\n"
    )
    return target


@pytest.mark.component
@pytest.mark.parametrize("forking_requested", [True, False])
def test_worker_process_executor_supplies_worker_id(tmp_path, forking_requested):
    """A Worker constructed with worker_id="gw3" makes config.workerinput
    visible to every dispatched pytest run, whether the Worker lands on the
    forking or the subprocess executor — the same mechanism (env var +
    `-p` module plugin) has to cross both boundaries identically."""
    target = _write_workerinput_probe_project(tmp_path)
    executor = WorkerProcessExecutor(
        worker_root=str(tmp_path), guarded_path=str(target), forking_requested=forking_requested, worker_id="gw3"
    )
    executor.prime()
    try:
        assert executor.run(["-q", "tests/test_worker_id.py"], timeout=30.0) == "survived"
    finally:
        executor.close()


@pytest.mark.component
def test_worker_process_executor_without_worker_id_leaves_workerinput_unset(tmp_path):
    (tmp_path / "conftest.py").write_text("")
    target = tmp_path / "calc.py"
    target.write_text("def add(a, b):\n    return a + b\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_no_worker_id.py").write_text(
        "from calc import add\n"
        "def test_no_workerinput(request):\n"
        "    assert not hasattr(request.config, 'workerinput')\n"
        "    assert add(2, 2) == 4\n"
    )
    executor = WorkerProcessExecutor(worker_root=str(tmp_path), guarded_path=str(target), forking_requested=True)
    executor.prime()
    try:
        assert executor.run(["-q", "tests/test_no_worker_id.py"], timeout=30.0) == "survived"
    finally:
        executor.close()


# --- forking vs. subprocess parity within a Worker -----------------------------


@pytest.mark.component
def test_worker_forking_and_subprocess_parity(tmp_path):
    """Two real Worker subprocesses, one forced to the subprocess executor,
    must classify an identical mutant identically."""
    (tmp_path / "conftest.py").write_text("")
    target = tmp_path / "calc.py"
    target.write_text("def add(a, b):\n    return a + b\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_calc.py").write_text("from calc import add\ndef test_add():\n    assert add(2, 2) == 4\n")
    args = ["-q", "tests"]

    forking_worker = WorkerProcessExecutor(worker_root=str(tmp_path), guarded_path=str(target), forking_requested=True)
    subprocess_worker = WorkerProcessExecutor(
        worker_root=str(tmp_path), guarded_path=str(target), forking_requested=False
    )
    forking_worker.prime()
    subprocess_worker.prime()
    try:
        assert forking_worker.run(args, timeout=30.0) == "survived"
        assert subprocess_worker.run(args, timeout=30.0) == "survived"

        target.write_text("def add(a, b):\n    return a - b\n")
        assert forking_worker.run(args, timeout=30.0) == "killed"
        assert subprocess_worker.run(args, timeout=30.0) == "killed"
    finally:
        forking_worker.close()
        subprocess_worker.close()


# --- a leaked target inside a Worker degrades to the subprocess executor ------


@pytest.mark.component
def test_worker_server_degrades_to_subprocess_on_leaked_target(tmp_path, monkeypatch, capfd):
    """A module-leak has to happen in the Worker subprocess's own
    sys.modules; a real subprocess boundary can't be seeded from outside, so
    this drives `_worker_server.main` directly in-process instead — the same
    code a real Worker subprocess runs, with a pre-seeded fake leaked module
    standing in for the leak.

    Captures the real OS fd 1 with a raw pipe inside `capfd.disabled()`:
    `_run_pytest_output_suppressed`'s flush-before-dup2 fix operates on the
    real fd, and pytest's own fd-capture layering (already active for the
    whole test session) has to be suspended first, or its dup2 bookkeeping
    fights our own and masks exactly the framing bug this test exists to
    catch."""
    import mutate4py._forking_executor as forking_mod
    import mutate4py._subprocess_executor as subprocess_mod
    import mutate4py._worker_server as worker_server_mod

    (tmp_path / "conftest.py").write_text("")
    target = tmp_path / "calc.py"
    target.write_text("def add(a, b):\n    return a + b\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_calc.py").write_text("from calc import add\ndef test_add():\n    assert add(2, 2) == 4\n")

    fake_module = types.ModuleType("calc")
    fake_module.__file__ = str(target)
    monkeypatch.setitem(sys.modules, "calc", fake_module)

    created_forking = []
    created_subprocess = []
    real_forking_cls = forking_mod.ForkingExecutor
    real_subprocess_cls = subprocess_mod.SubprocessExecutor

    class _TrackingForkingExecutor(real_forking_cls):
        def __init__(self, *a, **kw):
            created_forking.append(self)
            super().__init__(*a, **kw)

    class _TrackingSubprocessExecutor(real_subprocess_cls):
        def __init__(self, *a, **kw):
            created_subprocess.append(self)
            super().__init__(*a, **kw)

    monkeypatch.setattr(forking_mod, "ForkingExecutor", _TrackingForkingExecutor)
    monkeypatch.setattr(subprocess_mod, "SubprocessExecutor", _TrackingSubprocessExecutor)

    stdin = io.StringIO(json.dumps({"args": ["-q", "tests"], "timeout": 30.0}) + "\n")
    monkeypatch.setattr(sys, "stdin", stdin)

    with capfd.disabled():
        read_fd, write_fd = os.pipe()
        saved_stdout_fd = os.dup(1)
        os.dup2(write_fd, 1)
        os.close(write_fd)
        try:
            worker_server_mod.main([str(tmp_path), str(target), "1"])
            sys.stdout.flush()
        finally:
            os.dup2(saved_stdout_fd, 1)
            os.close(saved_stdout_fd)
        captured_out = os.read(read_fd, 65536).decode()
        os.close(read_fd)

    lines = captured_out.splitlines()
    assert json.loads(lines[0]) == {"ready": True}
    assert json.loads(lines[1])["status"] == "survived"
    assert len(created_forking) == 1, "expected the forking executor to be attempted once"
    assert len(created_subprocess) == 1, "expected the self-leak to fall back to the subprocess executor"
