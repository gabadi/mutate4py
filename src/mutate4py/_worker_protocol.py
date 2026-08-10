"""Orchestrator-side proxy for a Worker subprocess (issue 04b): implements
the `Executor` protocol by spawning `_worker_server.py` once and holding its
stdin/stdout pipes open for the Worker's whole run, dispatching one JSON
line per Mutant rather than spawning a fresh process per Mutant. Worker
process identity stays stable across dispatches.
"""

import json
import subprocess
import sys

__all__ = ["WorkerProcessError", "WorkerProcessExecutor"]


class WorkerProcessError(Exception):
    """The Worker subprocess exited, or answered outside the protocol."""


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
            [
                sys.executable,
                "-m",
                "mutate4py._worker_server",
                self._worker_root,
                self._guarded_path,
                "1" if self._forking_requested else "0",
                self._worker_id or "",
            ],
            cwd=self._worker_root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        ready_line = self._proc.stdout.readline()
        if not ready_line:
            raise WorkerProcessError(f"worker process at {self._worker_root!r} exited before signaling ready")
        json.loads(ready_line)

    def run(self, args: list[str], timeout: float) -> str:
        if self._proc is None:
            raise WorkerProcessError("prime() must succeed before run()")
        self._proc.stdin.write(json.dumps({"args": args, "timeout": timeout}) + "\n")
        self._proc.stdin.flush()
        response_line = self._proc.stdout.readline()
        if not response_line:
            raise WorkerProcessError(f"worker process at {self._worker_root!r} closed its output unexpectedly")
        return json.loads(response_line)["status"]

    def close(self) -> None:
        if self._proc is None:
            return
        self._proc.stdin.close()
        try:
            self._proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait()
