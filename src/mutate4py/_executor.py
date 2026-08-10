"""The executor interface both mutant-execution paths implement: prime once
for a given `cwd`, then run a given pytest argument list under a timeout and
report how the mutant classified.

`ForkingExecutor` (`_forking_executor.py`) and `SubprocessExecutor`
(`_subprocess_executor.py`) both satisfy this structurally — no inheritance
required, so the run loop that only ever holds `Executor` never needs to
know which one it has.
"""

from typing import Protocol

__all__ = ["Executor"]


class Executor(Protocol):
    def prime(self) -> None: ...

    def run(self, args: list[str], timeout: float) -> str: ...
