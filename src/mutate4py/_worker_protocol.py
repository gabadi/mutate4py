"""Orchestrator-side proxy for a Worker subprocess: implements
the `Executor` protocol by spawning `_worker_server.py` once and holding its
stdin/stdout pipes open for the Worker's whole run, dispatching one JSON
line per Mutant rather than spawning a fresh process per Mutant. Worker
process identity stays stable across dispatches.
"""

import json
import os
import subprocess

__all__ = [
    "WorkerProcessError",
    "WorkerProcessExecutor",
    "encode_request",
    "check_worker_pytest",
    "check_worker_python",
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


def worker_server_argv(
    *, worker_root: str, guarded_path: str, forking_requested: bool, worker_id: str | None
) -> list[str]:
    """Argv that starts one `_worker_server` for this Worker.

    Every element is a string because it crosses a process boundary as argv:
    the forking request becomes "1"/"0" and an absent worker_id becomes "",
    which `_worker_server.main` reads back as None.
    """
    return [
        worker_python(worker_root),
        "-m",
        "mutate4py._worker_server",
        worker_root,
        guarded_path,
        "1" if forking_requested else "0",
        worker_id or "",
    ]


def encode_request(args: list[str], timeout: float) -> str:
    """One dispatch as the newline-terminated JSON line `_serve` reads."""
    return json.dumps({"args": args, "timeout": timeout}) + "\n"


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
        forking_requested: bool,
        source_root: str,
        worker_id: str | None = None,
    ) -> None:
        self._worker_root = worker_root
        self._guarded_path = guarded_path
        self._forking_requested = forking_requested
        self._source_root = source_root
        self._worker_id = worker_id
        self._proc: subprocess.Popen | None = None

    def prime(self) -> None:
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
                worker_server_argv(
                    worker_root=self._worker_root,
                    guarded_path=self._guarded_path,
                    forking_requested=self._forking_requested,
                    worker_id=self._worker_id,
                ),
                cwd=self._worker_root,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as e:
            raise WorkerProcessError(
                f"worker interpreter {worker_python(self._worker_root)!r} could not be started: {e}"
            ) from e
        _decode_ready(self._proc.stdout.readline(), worker_root=self._worker_root)

    def run(self, args: list[str], timeout: float) -> str:
        if self._proc is None:
            raise WorkerProcessError("prime() must succeed before run()")
        self._proc.stdin.write(encode_request(args, timeout))
        self._proc.stdin.flush()
        return _decode_status(self._proc.stdout.readline(), worker_root=self._worker_root)

    def close(self) -> None:
        if self._proc is None:
            return
        _shutdown_process(self._proc)
