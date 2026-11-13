"""Shared test doubles for the Worker tests (test_workers.py and
test_workers_dispatch.py): a lock-guarded fake Executor and a no-op result sink."""

import threading


def noop_on_result(result: dict) -> None:
    pass


class FakeExecutor:
    """Minimal stand-in for the Executor protocol: no forking, no subprocess.

    Lock-guarded so multiple Worker threads can share one instance (as
    happens when a test injects a single fake executor at max_workers>=2)
    without racing on prime_calls/calls.
    """

    def __init__(self, status: str) -> None:
        self._status = status
        self._lock = threading.Lock()
        self.calls: list[list[str]] = []
        self.prime_calls = 0

    def prime(self) -> None:
        with self._lock:
            self.prime_calls += 1

    def run(self, args: list[str], timeout: float) -> str:
        with self._lock:
            self.calls.append(args)
        return self._status
