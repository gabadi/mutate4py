"""The subprocess executor: the always-available mutant-execution path, one
fresh pytest process per call — via `sys.executable -m pytest`, so it always
resolves to the same interpreter's pytest as the forking executor's
in-process import, never PATH- or shell-resolved. `prime()` is a no-op:
there is nothing to warm, unlike the forking executor. Each child gets
PYTHONDONTWRITEBYTECODE=1, mirroring the forking path's `dont_write_bytecode`,
and the guarded file's cached bytecode is removed before each run, as the
forking path does, so no child can load a stale .pyc (#81).
"""

import os
import sys

from mutate4py._bytecode_cache import invalidate_bytecode_cache
from mutate4py._cmd import run_argv

__all__ = ["SubprocessExecutor"]


class SubprocessExecutor:
    def __init__(self, cwd: str, guarded_path: str) -> None:
        self._cwd = cwd
        self._guarded_path = guarded_path

    def prime(self) -> None:
        pass

    def run(self, args: list[str], timeout: float) -> str:
        invalidate_bytecode_cache(self._guarded_path)
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        return run_argv([sys.executable, "-m", "pytest", *args], self._cwd, timeout, env=env)
