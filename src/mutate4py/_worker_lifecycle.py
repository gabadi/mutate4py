"""The failures of a parallel run and the lifecycle calls a Worker's executor gets from it: prime, describe and
close, with a protocol failure restated as the Worker failure the run loop reports.
"""

from mutate4py._executor import Executor, ExecutorDescription
from mutate4py._worker_protocol import WorkerProcessError

__all__ = [
    "ParallelRunError",
    "WorkerFailureError",
    "_close_worker_executor",
    "_describe_worker_executor",
    "_prime_worker_executor",
]


class ParallelRunError(Exception):
    pass


class WorkerFailureError(ParallelRunError):
    pass


def _prime_worker_executor(executor: Executor, worker_idx: int) -> None:
    """Prime this Worker's executor, restating a protocol failure as the
    Worker failure the run loop reports."""
    try:
        executor.prime()
    except WorkerProcessError as e:
        raise WorkerFailureError(f"worker-{worker_idx} could not start: {e}") from e


def _describe_worker_executor(executor: Executor, worker_idx: int) -> ExecutorDescription:
    """Ask this Worker's primed executor how it runs its Mutants, restating a
    protocol failure as the Worker failure the run loop reports."""
    try:
        return executor.describe()
    except WorkerProcessError as e:
        raise WorkerFailureError(f"worker-{worker_idx} could not describe its executor: {e}") from e


def _close_worker_executor(executor: Executor) -> None:
    """Close the executor if it has anything to close: `Executor` does not
    require close(), and the injected test executor has none."""
    close = getattr(executor, "close", None)
    if close is not None:
        close()
