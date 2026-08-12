"""Orchestrator-side proxy for a Worker subprocess: implements
the `Executor` protocol by spawning `_worker_server.py` once and holding its
stdin/stdout pipes open for the Worker's whole run, dispatching one JSON
line per Mutant rather than spawning a fresh process per Mutant. Worker
process identity stays stable across dispatches.
"""

import json
import subprocess
import sys

__all__ = [
    "WorkerProcessError",
    "WorkerProcessExecutor",
    "encode_request",
    "worker_server_argv",
]

_SHUTDOWN_GRACE_SECONDS = 10


class WorkerProcessError(Exception):
    """The Worker subprocess exited, or answered outside the protocol."""


def worker_server_argv(
    *, worker_root: str, guarded_path: str, forking_requested: bool, worker_id: str | None
) -> list[str]:
    """Argv that starts one `_worker_server` for this Worker.

    Every element is a string because it crosses a process boundary as argv:
    the forking request becomes "1"/"0" and an absent worker_id becomes "",
    which `_worker_server.main` reads back as None.
    """
    return [
        sys.executable,
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


class WorkerProcessExecutor:
    """One persistent Worker subprocess, primed once, dispatched by line."""

    def __init__(
        self, *, worker_root: str, guarded_path: str, forking_requested: bool, worker_id: str | None = None
    ) -> None:
        self._worker_root = worker_root
        self._guarded_path = guarded_path
        self._forking_requested = forking_requested
        self._worker_id = worker_id
        self._proc: subprocess.Popen | None = None

    def prime(self) -> None:
        self._proc = subprocess.Popen(
            worker_server_argv(
                worker_root=self._worker_root,
                guarded_path=self._guarded_path,
                forking_requested=self._forking_requested,
                worker_id=self._worker_id,
            ),
            cwd=self._worker_root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
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
