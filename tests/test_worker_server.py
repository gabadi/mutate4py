"""Unit tests for _worker_server's startup argv decoding and for _serve's
Django-worker-plugin arg injection (issue 05) — a fake Executor, no real
subprocess/pytest. Companion to the real-process round trips in
test_worker_protocol.py.
"""

import io
import json

from mutate4py._executor import ExecutorDescription
import mutate4py._worker_server as worker_server_mod
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
def test_parse_worker_argv_reads_an_empty_or_missing_ran_at_import_slot_as_no_lines():
    assert parse_worker_argv(["/w", "/w/calc.py", "1", "", ""]).ran_at_import == frozenset()
    assert parse_worker_argv(["/w", "/w/calc.py", "1", ""]).ran_at_import == frozenset()


@pytest.mark.unit
def test_parse_worker_argv_reads_the_ran_at_import_lines_and_the_prime_args_after_them():
    args = parse_worker_argv(["/w", "/w/calc.py", "1", "", "4,7", "-p", "no:tach"])
    assert (args.ran_at_import, args.prime_args) == (frozenset({4, 7}), ("-p", "no:tach"))


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
        self.controls: list[bool] = []

    def run(self, args: list[str], timeout: float, *, control: bool = False) -> str:
        self.calls.append(args)
        self.controls.append(control)
        return "survived"


def _drive(executor, plugin_args, *requests, neutralise=lambda args: []):
    instream = io.StringIO("".join(json.dumps(r) + "\n" for r in requests))
    outstream = io.StringIO()
    _serve(executor, instream, outstream, plugin_args=plugin_args, neutralise=neutralise)
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


@pytest.mark.unit
def test_serve_tells_the_executor_which_dispatch_is_a_control_run():
    """The request carries `control` for a Control run only; the executor leaves such a run out of its counts."""
    executor = _RecordingExecutor()
    _drive(
        executor,
        [],
        {"args": ["-q", "a"], "timeout": 5.0},
        {"args": ["-q", "a"], "timeout": 5.0, "control": True},
    )
    assert executor.controls == [False, True]


class _DescribingExecutor(_RecordingExecutor):
    def describe(self) -> ExecutorDescription:
        return ExecutorDescription(mode="subprocess", reason="--no-fork")


@pytest.mark.unit
def test_serve_answers_a_describe_request_with_its_executors_description_and_runs_nothing():
    executor = _DescribingExecutor()
    outstream = io.StringIO()
    _serve(
        executor,
        io.StringIO(json.dumps({"describe": True}) + "\n"),
        outstream,
        plugin_args=[],
        neutralise=lambda args: [],
    )
    assert json.loads(outstream.getvalue()) == {
        "description": {
            "mode": "subprocess",
            "reason": "--no-fork",
            "fresh_import": 0,
            "swap": 0,
            "fresh_interpreter": 0,
        }
    }
    assert executor.calls == []


# ── plugin args ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_worker_plugin_args_loads_the_django_plugin_for_a_worker_with_an_id():
    assert _worker_plugin_args("gw1") == ["-p", "mutate4py._django_worker_plugin"]


@pytest.mark.unit
def test_worker_plugin_args_is_empty_for_a_worker_without_an_id():
    assert _worker_plugin_args(None) == []


@pytest.mark.unit
def test_serve_asks_for_the_kill_switches_of_each_dispatchs_own_args_and_puts_them_before_the_plugin_args():
    executor = _RecordingExecutor()
    asked = []

    def neutralise(args):
        asked.append(list(args))
        return ["--no-cov"] if "-p" in args else []

    _drive(
        executor,
        ["-p", "mutate4py._django_worker_plugin"],
        {"args": ["-q", "-p", "pytest_cov"], "timeout": 5.0},
        {"args": ["-q"], "timeout": 5.0},
        neutralise=neutralise,
    )
    assert asked == [["-q", "-p", "pytest_cov"], ["-q"]]
    assert executor.calls == [
        ["-q", "-p", "pytest_cov", "--no-cov", "-p", "mutate4py._django_worker_plugin"],
        ["-q", "-p", "mutate4py._django_worker_plugin"],
    ]


@pytest.mark.unit
def test_main_asks_for_the_kill_switches_in_the_workers_own_directory(monkeypatch):
    """A Worker reads its project's inifile and conftests, so the switches are chosen for its cwd."""
    executor = _RecordingExecutor()
    asked = []

    def fake_neutralising_args(pytest_args, cwd):
        asked.append((list(pytest_args), cwd))
        return ["--fake-flag"]

    monkeypatch.setattr(worker_server_mod, "neutralising_args", fake_neutralising_args)
    monkeypatch.setattr(worker_server_mod, "_prepare_executor", lambda **_: executor)
    monkeypatch.setattr(
        worker_server_mod.sys, "stdin", io.StringIO(json.dumps({"args": ["-q"], "timeout": 1.0}) + "\n")
    )
    stdout = io.StringIO()
    monkeypatch.setattr(worker_server_mod.sys, "stdout", stdout)

    worker_server_mod.main(["/the/worker/cwd", "/the/worker/cwd/calc.py", "0"])

    assert [json.loads(line) for line in stdout.getvalue().splitlines()] == [{"ready": True}, {"status": "survived"}]
    assert asked == [(["-q"], "/the/worker/cwd")]
    assert executor.calls == [["-q", "--fake-flag"]]
