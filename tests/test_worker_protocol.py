"""Tests for issue 04b: the Worker subprocess protocol
(`_worker_protocol.WorkerProcessExecutor` <-> `_worker_server.main`).

Two layers. The unit section below covers the protocol's pure pieces — argv,
request encoding, response decoding, shutdown — against fakes. Everything
after it is component-level: real subprocesses, real pytest, no fakes.
Companion to the fake-executor unit tests in test_workers.py, which cover the
same dispatch logic without paying for a real subprocess spawn.
"""

import io
import json
import os
import subprocess
import sys
import types

import pytest

from mutate4py._worker_protocol import (
    WorkerProcessError,
    WorkerProcessExecutor,
    _decode_ready,
    _decode_status,
    _shutdown_process,
    encode_request,
    worker_server_argv,
)


# ── argv and request encoding ─────────────────────────────────────────────


@pytest.mark.unit
def test_worker_server_argv_names_the_worker_server_module():
    argv = worker_server_argv(worker_root="/w", guarded_path="/w/calc.py", forking_requested=True, worker_id="gw1")
    assert argv == [sys.executable, "-m", "mutate4py._worker_server", "/w", "/w/calc.py", "1", "gw1"]


@pytest.mark.unit
def test_worker_server_argv_encodes_a_declined_fork_request_as_zero():
    argv = worker_server_argv(worker_root="/w", guarded_path="/w/calc.py", forking_requested=False, worker_id="gw1")
    assert argv[5] == "0"


@pytest.mark.unit
def test_worker_server_argv_encodes_an_absent_worker_id_as_an_empty_string():
    argv = worker_server_argv(worker_root="/w", guarded_path="/w/calc.py", forking_requested=True, worker_id=None)
    assert argv[6] == ""


@pytest.mark.unit
def test_encode_request_is_one_newline_terminated_json_line():
    line = encode_request(["-q", "tests"], 30.0)
    assert line.endswith("\n")
    assert json.loads(line) == {"args": ["-q", "tests"], "timeout": 30.0}


# ── response decoding ─────────────────────────────────────────────────────


@pytest.mark.unit
def test_decode_ready_accepts_the_handshake_line():
    assert _decode_ready(json.dumps({"ready": True}) + "\n", worker_root="/w") is None


@pytest.mark.unit
def test_decode_ready_raises_when_the_worker_died_before_the_handshake():
    with pytest.raises(WorkerProcessError, match="exited before signaling ready"):
        _decode_ready("", worker_root="/w")


@pytest.mark.unit
def test_decode_status_returns_the_classification():
    assert _decode_status(json.dumps({"status": "killed"}) + "\n", worker_root="/w") == "killed"


@pytest.mark.unit
def test_decode_status_raises_when_the_pipe_closed_mid_run():
    with pytest.raises(WorkerProcessError, match="closed its output unexpectedly"):
        _decode_status("", worker_root="/w")


# ── shutdown ──────────────────────────────────────────────────────────────


class _FakeStdin:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _FakeProc:
    """A Popen stand-in that records the shutdown sequence it was put through."""

    def __init__(self, *, waits_time_out: bool):
        self.stdin = _FakeStdin()
        self._waits_time_out = waits_time_out
        self.calls: list[str] = []

    def wait(self, timeout=None):
        self.calls.append("wait")
        if self._waits_time_out and len(self.calls) == 1:
            raise subprocess.TimeoutExpired(cmd="worker", timeout=timeout)

    def kill(self):
        self.calls.append("kill")


@pytest.mark.unit
def test_shutdown_process_closes_stdin_and_waits_for_a_cooperative_worker():
    proc = _FakeProc(waits_time_out=False)
    _shutdown_process(proc)
    assert proc.stdin.closed
    assert proc.calls == ["wait"]


@pytest.mark.unit
def test_shutdown_process_kills_a_worker_that_outstays_the_grace_period():
    proc = _FakeProc(waits_time_out=True)
    _shutdown_process(proc)
    assert proc.calls == ["wait", "kill", "wait"]


# ── priming preconditions ─────────────────────────────────────────────────


@pytest.mark.unit
def test_run_before_prime_is_rejected():
    executor = WorkerProcessExecutor(worker_root="/w", guarded_path="/w/calc.py", forking_requested=True)
    with pytest.raises(WorkerProcessError, match="prime\\(\\) must succeed before run\\(\\)"):
        executor.run(["-q"], timeout=1.0)


@pytest.mark.unit
def test_close_before_prime_is_a_no_op():
    executor = WorkerProcessExecutor(worker_root="/w", guarded_path="/w/calc.py", forking_requested=True)
    executor.close()


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
