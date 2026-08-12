"""Unit tests for _worker_server's startup argv decoding and for _serve's
Django-worker-plugin arg injection (issue 05) — a fake Executor, no real
subprocess/pytest. Companion to the real-process round trips in
test_worker_protocol.py.
"""

import io
import json

from mutate4py._worker_server import _serve, parse_worker_argv, worker_environ_updates
import pytest


# ── startup argv ──────────────────────────────────────────────────────────


@pytest.mark.unit
def test_parse_worker_argv_reads_every_slot():
    args = parse_worker_argv(["/w", "/w/calc.py", "1", "gw2"])
    assert (args.cwd, args.guarded_path, args.forking_requested, args.worker_id) == ("/w", "/w/calc.py", True, "gw2")


@pytest.mark.unit
def test_parse_worker_argv_reads_a_declined_fork_request():
    assert parse_worker_argv(["/w", "/w/calc.py", "0", "gw2"]).forking_requested is False


@pytest.mark.unit
def test_parse_worker_argv_treats_an_empty_worker_id_slot_as_absent():
    assert parse_worker_argv(["/w", "/w/calc.py", "1", ""]).worker_id is None


@pytest.mark.unit
def test_parse_worker_argv_treats_a_missing_worker_id_slot_as_absent():
    assert parse_worker_argv(["/w", "/w/calc.py", "1"]).worker_id is None


@pytest.mark.unit
def test_worker_environ_updates_exports_the_worker_id():
    assert worker_environ_updates("gw2") == {"MUTATE4PY_WORKER_ID": "gw2"}


@pytest.mark.unit
def test_worker_environ_updates_is_empty_without_a_worker_id():
    assert worker_environ_updates(None) == {}


# ── _serve ────────────────────────────────────────────────────────────────


class _RecordingExecutor:
    def __init__(self):
        self.calls: list[list[str]] = []

    def run(self, args: list[str], timeout: float) -> str:
        self.calls.append(args)
        return "survived"


def _drive(executor, worker_id, *requests):
    instream = io.StringIO("".join(json.dumps(r) + "\n" for r in requests))
    outstream = io.StringIO()
    _serve(executor, instream, outstream, worker_id=worker_id)
    return [json.loads(line)["status"] for line in outstream.getvalue().splitlines()]


@pytest.mark.unit
def test_serve_appends_plugin_args_when_worker_id_set():
    executor = _RecordingExecutor()
    _drive(executor, "gw2", {"args": ["-q", "tests"], "timeout": 5.0})
    assert executor.calls == [["-q", "tests", "-p", "mutate4py._django_worker_plugin"]]


@pytest.mark.unit
def test_serve_leaves_args_untouched_without_worker_id():
    executor = _RecordingExecutor()
    _drive(executor, None, {"args": ["-q", "tests"], "timeout": 5.0})
    assert executor.calls == [["-q", "tests"]]


@pytest.mark.unit
def test_serve_appends_plugin_args_on_every_dispatch():
    executor = _RecordingExecutor()
    _drive(
        executor,
        "gw0",
        {"args": ["-q", "a"], "timeout": 5.0},
        {"args": ["-q", "b"], "timeout": 5.0},
    )
    assert executor.calls == [
        ["-q", "a", "-p", "mutate4py._django_worker_plugin"],
        ["-q", "b", "-p", "mutate4py._django_worker_plugin"],
    ]
