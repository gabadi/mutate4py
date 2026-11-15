"""Orchestrator-side proxy for a Worker subprocess: implements
the `Executor` protocol by spawning `_worker_server.py` once and holding its
stdin/stdout pipes open for the Worker's whole run, dispatching one JSON
line per Mutant rather than spawning a fresh process per Mutant. Worker
process identity stays stable across dispatches.
"""

import dataclasses
import json
import os
import subprocess
import sys
from collections.abc import Sequence

from mutate4py._executor import ExecutorDescription

__all__ = [
    "FreshInterpreterRuns",
    "WorkerProcessError",
    "ServerLaunch",
    "WorkerProcessExecutor",
    "encode_describe",
    "encode_request",
    "check_worker_pytest",
    "check_worker_python",
    "fork_server",
    "worker_python",
    "worker_server_argv",
]

_SHUTDOWN_GRACE_SECONDS = 10

# mutate4py needs Python 3.11; a Worker venv below it cannot run the worker server.
WORKER_PYTHON_FLOOR = (3, 11)


class WorkerProcessError(Exception):
    """The Worker subprocess exited, or answered outside the protocol."""


def worker_python(worker_root: str) -> str:
    """The Worker's own provisioned interpreter. Everything that runs pytest
    for this Worker runs under it, so the plugins it sees (and the kill
    switches computed for them) are the Worker venv's, not the orchestrator's."""
    return os.path.join(os.path.abspath(worker_root), ".venv", "bin", "python")


def check_worker_python(worker_root: str) -> None:
    """Refuse a Worker venv whose interpreter cannot run mutate4py, naming both
    versions, so the run fails before any Mutant is dispatched."""
    try:
        probe = subprocess.run(
            [worker_python(worker_root), "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as e:
        raise WorkerProcessError(f"worker venv at {worker_root!r} has no usable interpreter: {e}") from e
    version = probe.stdout.strip()
    if tuple(int(part) for part in version.split(".")) < WORKER_PYTHON_FLOOR:
        floor = ".".join(map(str, WORKER_PYTHON_FLOOR))
        raise WorkerProcessError(
            f"worker venv at {worker_root!r} runs Python {version}; mutate4py Workers need Python >= {floor}"
        )


def check_worker_pytest(worker_root: str) -> None:
    """Refuse a Worker venv that cannot import pytest: every Mutant would exit 1
    and read as killed. ADR 0015: strict all-or-nothing, no silent degrade."""
    python = worker_python(worker_root)
    try:
        probe = subprocess.run([python, "-c", "import pytest"], capture_output=True, cwd=worker_root)
    except OSError as e:
        raise WorkerProcessError(f"worker interpreter {python!r} could not be started: {e}") from e
    if probe.returncode:
        raise WorkerProcessError(
            f"worker environment {worker_root} has no pytest; "
            "declare pytest in the project's dev dependencies so `uv sync` installs it"
        )


@dataclasses.dataclass(frozen=True)
class ServerLaunch:
    """How one Worker server starts, beyond the tree it serves and the file it guards.

    `forking_requested` asks it to prime the forking executor; `worker_id` is the
    Worker's identity (None for a fork server); `prime_args` are the run's own
    `-p no:<name>` blocks the forking executor primes with; `python` is the
    interpreter it runs under, None meaning the Worker venv's own (which must
    import pytest, checked at prime). A fork server runs under the Project
    environment's instead (`fork_server`). `ran_at_import` are the guarded
    file's lines the Measurement saw run under the Empty context, which swap
    mode refuses to swap.
    """

    forking_requested: bool = True
    worker_id: str | None = None
    prime_args: tuple[str, ...] = ()
    python: str | None = None
    ran_at_import: frozenset[int] = frozenset()


def _launch_python(worker_root: str, launch: ServerLaunch) -> str:
    return launch.python or worker_python(worker_root)


def worker_server_argv(*, worker_root: str, guarded_path: str, launch: ServerLaunch) -> list[str]:
    """Argv that starts one `_worker_server` for this Worker.

    Every element is a string because it crosses a process boundary as argv:
    the forking request becomes "1"/"0", an absent worker_id becomes "",
    which `_worker_server.main` reads back as None, and the ran-at-import lines
    become one comma-joined slot. The prime args follow.
    """
    return [
        _launch_python(worker_root, launch),
        "-m",
        "mutate4py._worker_server",
        worker_root,
        guarded_path,
        "1" if launch.forking_requested else "0",
        launch.worker_id or "",
        ",".join(str(line) for line in sorted(launch.ran_at_import)),
        *launch.prime_args,
    ]


def encode_request(args: list[str], timeout: float, *, control: bool = False, fresh: bool = False) -> str:
    """One dispatch as the newline-terminated JSON line `_serve` reads; a Control run and a fresh run say so."""
    request: dict[str, object] = {"args": args, "timeout": timeout}
    if control:
        request["control"] = True
    if fresh:
        request["fresh"] = True
    return json.dumps(request) + "\n"


def encode_describe() -> str:
    """The request asking a Worker to describe its executor, as the line `_serve` reads."""
    return json.dumps({"describe": True}) + "\n"


def _decode_ready(line: str, *, worker_root: str) -> None:
    """Consume the Worker's one-line ready handshake."""
    if not line:
        raise WorkerProcessError(f"worker process at {worker_root!r} exited before signaling ready")
    json.loads(line)


def _decode_status(line: str, *, worker_root: str) -> str:
    """The classification carried by one response line."""
    if not line:
        raise WorkerProcessError(f"worker process at {worker_root!r} closed its output unexpectedly")
    return json.loads(line)["status"]


def _decode_description(line: str, *, worker_root: str) -> ExecutorDescription:
    """The executor description one describe response carries, rebuilt on this side."""
    if not line:
        raise WorkerProcessError(f"worker process at {worker_root!r} closed its output unexpectedly")
    return ExecutorDescription(**json.loads(line)["description"])


def _shutdown_process(proc: subprocess.Popen[str]) -> None:
    """Close the Worker's stdin and wait for it to exit, killing it if it
    outstays the grace period — a Worker that ignores its closed stdin must
    never wedge the whole run."""
    proc.stdin.close()
    try:
        proc.wait(timeout=_SHUTDOWN_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _worker_pythonpath(worker_root: str, source_root: str) -> str | None:
    """The caller's PYTHONPATH for the Worker, or None when the caller set none. An entry
    inside the project is rebased onto the Worker's copy, so the Worker imports its
    mutated source and never the original one the caller points at."""
    source_root = os.path.realpath(source_root)
    entries = []
    for entry in filter(None, os.environ.get("PYTHONPATH", "").split(os.pathsep)):
        real = os.path.realpath(entry)
        if real == source_root or real.startswith(source_root + os.sep):
            entry = os.path.join(worker_root, os.path.relpath(real, source_root))
        entries.append(entry)
    return os.pathsep.join(entries) if entries else None


class WorkerProcessExecutor:
    """One persistent Worker subprocess, primed once, dispatched by line."""

    def __init__(
        self,
        *,
        worker_root: str,
        guarded_path: str,
        source_root: str,
        launch: ServerLaunch,
    ) -> None:
        self._worker_root = worker_root
        self._guarded_path = guarded_path
        self._source_root = source_root
        self.launch = launch
        self._proc: subprocess.Popen | None = None

    def prime(self) -> None:
        if self.launch.python is None:
            check_worker_pytest(self._worker_root)
        # The import root is not on PYTHONPATH: _workers links it as a `.pth` in the
        # Worker venv, read after site-packages, so the Worker's own mutate4py wins.
        env = dict(os.environ)
        pythonpath = _worker_pythonpath(self._worker_root, self._source_root)
        if pythonpath is None:
            env.pop("PYTHONPATH", None)
        else:
            env["PYTHONPATH"] = pythonpath
        try:
            self._proc = subprocess.Popen(
                worker_server_argv(worker_root=self._worker_root, guarded_path=self._guarded_path, launch=self.launch),
                cwd=self._worker_root,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as e:
            raise WorkerProcessError(
                f"worker interpreter {_launch_python(self._worker_root, self.launch)!r} could not be started: {e}"
            ) from e
        _decode_ready(self._proc.stdout.readline(), worker_root=self._worker_root)

    def run(self, args: list[str], timeout: float, *, control: bool = False, fresh: bool = False) -> str:
        if self._proc is None:
            raise WorkerProcessError("prime() must succeed before run()")
        self._proc.stdin.write(encode_request(args, timeout, control=control, fresh=fresh))
        self._proc.stdin.flush()
        return _decode_status(self._proc.stdout.readline(), worker_root=self._worker_root)

    def fresh_interpreter(self) -> "FreshInterpreterRuns":
        return FreshInterpreterRuns(self)

    def describe(self) -> ExecutorDescription:
        if self._proc is None:
            raise WorkerProcessError("prime() must succeed before describe()")
        self._proc.stdin.write(encode_describe())
        self._proc.stdin.flush()
        return _decode_description(self._proc.stdout.readline(), worker_root=self._worker_root)

    def close(self) -> None:
        if self._proc is None:
            return
        _shutdown_process(self._proc)


class FreshInterpreterRuns:
    """The Worker's own fresh interpreter, reached over its pipe: each run asks the Worker server to start a
    `python -m pytest` under the Worker's interpreter, tree and environment, bypassing its forked children."""

    def __init__(self, worker: WorkerProcessExecutor) -> None:
        self._worker = worker

    def prime(self) -> None:
        pass

    def run(self, args: list[str], timeout: float, *, control: bool = False) -> str:
        return self._worker.run(args, timeout, control=control, fresh=True)

    def describe(self) -> ExecutorDescription:
        return self._worker.describe()

    def fresh_interpreter(self) -> "FreshInterpreterRuns":
        return self


def fork_server(
    *, cwd: str, guarded_path: str, prime_args: Sequence[str], ran_at_import: frozenset[int] = frozenset()
) -> WorkerProcessExecutor:
    """The executor a serial forking run primes: one Worker server over the
    project tree itself (no clone), under the Project environment this
    process runs in. It primes the forking executor, so the orchestrator,
    which has imported most of mutate4py and run the Measurement, never
    forks a Mutant. A server that cannot fork answers with the subprocess
    executor and says why."""
    return WorkerProcessExecutor(
        worker_root=cwd,
        guarded_path=guarded_path,
        source_root=cwd,
        launch=ServerLaunch(prime_args=tuple(prime_args), python=sys.executable, ran_at_import=ran_at_import),
    )
