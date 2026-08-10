"""The subprocess executor: the always-available mutant-execution path, one
fresh pytest process per call — via `sys.executable -m pytest`, so it always
resolves to the same interpreter's pytest as the forking executor's
in-process import, never PATH- or shell-resolved. `prime()` is a no-op:
there is nothing to warm, unlike the forking executor.
"""

import sys

from mutate4py._cmd import run_argv

__all__ = ["SubprocessExecutor"]


class SubprocessExecutor:
    def __init__(self, cwd: str) -> None:
        self._cwd = cwd

    def prime(self) -> None:
        pass

    def run(self, args: list[str], timeout: float) -> str:
        return run_argv([sys.executable, "-m", "pytest", *args], self._cwd, timeout)
