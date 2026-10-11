"""Unit tests for _worker_server's startup argv decoding and for _serve's
Django-worker-plugin arg injection (issue 05) — a fake Executor, no real
subprocess/pytest. Companion to the real-process round trips in
test_worker_protocol.py.
"""

import io
import json

from mutate4py import _worker_server
from mutate4py._worker_server import _serve, _worker_plugin_args, parse_worker_argv, worker_environ_updates
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


def _drive(executor, plugin_args, *requests):
    instream = io.StringIO("".join(json.dumps(r) + "\n" for r in requests))
    outstream = io.StringIO()
    _serve(executor, instream, outstream, plugin_args=plugin_args)
    return [json.loads(line)["status"] for line in outstream.getvalue().splitlines()]


@pytest.mark.unit
def test_serve_appends_plugin_args_to_every_dispatch():
    executor = _RecordingExecutor()
    statuses = _drive(
        executor,
        ["--no-cov", "-p", "mutate4py._django_worker_plugin"],
        {"args": ["-q", "a"], "timeout": 5.0},
        {"args": ["-q", "b"], "timeout": 5.0},
    )
    assert statuses == ["survived", "survived"]
    assert executor.calls == [
        ["-q", "a", "--no-cov", "-p", "mutate4py._django_worker_plugin"],
        ["-q", "b", "--no-cov", "-p", "mutate4py._django_worker_plugin"],
    ]


@pytest.mark.unit
def test_serve_leaves_args_untouched_when_there_are_no_plugin_args():
    executor = _RecordingExecutor()
    _drive(executor, [], {"args": ["-q", "tests"], "timeout": 5.0})
    assert executor.calls == [["-q", "tests"]]


# ── plugin args ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_worker_plugin_args_neutralises_then_loads_the_django_plugin_for_a_worker_with_an_id(monkeypatch):
    monkeypatch.setattr(_worker_server, "neutralising_args", lambda: ["--no-cov", "--benchmark-disable"])
    assert _worker_plugin_args("gw1") == [
        "--no-cov",
        "--benchmark-disable",
        "-p",
        "mutate4py._django_worker_plugin",
    ]


@pytest.mark.unit
def test_worker_plugin_args_without_a_worker_id_keeps_only_the_neutralising_args(monkeypatch):
    monkeypatch.setattr(_worker_server, "neutralising_args", lambda: ["--no-cov"])
    assert _worker_plugin_args(None) == ["--no-cov"]
