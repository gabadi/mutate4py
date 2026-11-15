"""A test Executor that answers each run from a script, shared by the serial loop's tests (test_execution.py)
and the Worker's (test_workers.py)."""

from mutate4py._executor import ExecutorDescription


class ScriptedExecutor:
    """Answers each run with the next scripted status and records, for each run, its argv and timeout and the
    text of the guarded file at the moment the run starts: what a Mutant or a Control run would have seen."""

    def __init__(self, path, statuses):
        self._path = path
        self._statuses = iter(statuses)
        self.calls: list[tuple[list[str], float]] = []
        self.seen_sources: list[str] = []

    def prime(self) -> None:
        pass

    def run(self, args, timeout):
        with open(self._path) as f:
            self.seen_sources.append(f.read())
        self.calls.append((list(args), timeout))
        return next(self._statuses)

    def describe(self) -> ExecutorDescription:
        return ExecutorDescription(mode="subprocess", reason="--no-fork")
