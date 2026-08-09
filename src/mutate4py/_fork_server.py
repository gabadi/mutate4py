"""Fork-server execution model for the serial mutation loop (issue #25).

A parent process primes pytest/plugins/framework setup once (running a
collect-only pass against an empty directory, so root conftest.py and
framework bootstrap — e.g. django.setup() — run without importing any real
test file), then fork()s a child per mutant. Each child calls pytest.main()
in-process, importing the guarded target file fresh, post-fork, from its
current (mutated) on-disk contents.

POSIX-only (requires os.fork). The parent must never import the guarded
target file before or between forks: a fork inherits the parent's
sys.modules, so a pre-imported target would make every child test
pre-mutation code and every mutant would falsely report as a survivor.
`assert_source_clean` enforces this after priming; `ForkServer.prime`
raises `ModuleLeakError` rather than silently proceeding unsafe.
"""

import importlib.util
import os
import shlex
import signal
import sys
import tempfile
import time

__all__ = [
    "ForkServer",
    "ForkServerUnavailable",
    "ModuleLeakError",
    "assert_source_clean",
    "is_available",
]

_POLL_INTERVAL = 0.01
# Args are passed straight to pytest.main(), never through a shell, so any of
# these in test_command would silently change meaning (e.g. "&&" becoming a
# literal pytest argument instead of a shell operator) rather than error out.
_SHELL_METACHARACTERS = set("&|;<>$`\\\n")


class ForkServerUnavailable(Exception):
    """Fork-server preconditions are not met; caller should fall back."""


class ModuleLeakError(ForkServerUnavailable):
    """The guarded target file is already present in sys.modules."""


def is_available(test_command: str) -> bool:
    """True if the platform and test_command shape support the fork server.

    Only a plain `pytest [args...]` command can reuse a primed pytest.main()
    child; anything else (a different runner, a shell pipeline) must keep
    using the per-mutant subprocess model.
    """
    if not hasattr(os, "fork"):
        return False
    if any(ch in test_command for ch in _SHELL_METACHARACTERS):
        return False
    try:
        tokens = shlex.split(test_command)
    except ValueError:
        return False
    return bool(tokens) and tokens[0] == "pytest"


def _leaked_modules(guarded_path: str) -> list[str]:
    real_guarded = os.path.realpath(guarded_path)
    leaked = []
    for name, mod in list(sys.modules.items()):
        mod_file = getattr(mod, "__file__", None)
        if mod_file and os.path.realpath(mod_file) == real_guarded:
            leaked.append(name)
    return leaked


def assert_source_clean(guarded_path: str) -> None:
    """Raise ModuleLeakError if guarded_path is already imported in this process.

    Any matching module is also evicted from sys.modules before raising, so a
    detected leak cannot persist and confuse a *different* file's leak check
    later in the same process (e.g. a directory batch run where two mutated
    files share a module name).
    """
    leaked = _leaked_modules(guarded_path)
    if leaked:
        for name in leaked:
            del sys.modules[name]
        raise ModuleLeakError(
            f"module(s) {leaked!r} already imported from {guarded_path}; "
            "the fork server cannot guarantee children re-read the mutated file"
        )


class ForkServer:
    """Primes pytest once for `cwd`, then forks a child per mutant.

    `guarded_path` must never be importable in this process before or
    between forks. Call `prime()` once; it raises `ForkServerUnavailable`
    (including the narrower `ModuleLeakError`) if the fast path is not safe
    for this project, in which case the caller should fall back to the
    existing per-mutant subprocess model instead of calling `run()`.
    """

    def __init__(self, cwd: str, extra_args: list[str], guarded_path: str) -> None:
        self._cwd = cwd
        self._extra_args = extra_args
        self._guarded_path = guarded_path
        self._primed = False

    def prime(self) -> None:
        try:
            import pytest
        except ImportError as exc:
            raise ForkServerUnavailable(f"pytest is not importable in this process: {exc}") from exc

        # Must live inside cwd (not system tmp): pytest's conftest.py
        # discovery walks from rootdir down to each collected path, so an
        # empty dir outside the project tree would never see the project's
        # own conftest.py (and whatever framework bootstrap it runs) at all
        # — defeating the whole point of priming.
        scratch_root = os.path.join(self._cwd, ".mutate4py", "forkserver")
        os.makedirs(scratch_root, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch_root, prefix="prime-") as empty_dir:
            _run_pytest_output_suppressed(pytest, ["--collect-only", "-q", empty_dir], self._cwd)

        assert_source_clean(self._guarded_path)
        self._primed = True

    def run(self, timeout: float) -> tuple[str, bool]:
        """Fork a child that runs the primed pytest.main() once.

        Returns (status, timed_out) with status in {killed, timeout,
        survived} — the same contract as `_cmd.run_command`.
        """
        if not self._primed:
            raise ForkServerUnavailable("prime() must succeed before run()")
        pid = os.fork()
        if pid == 0:
            self._run_child()
            os._exit(70)  # pragma: no cover - _run_child always calls os._exit
        return _wait_for_child(pid, timeout)

    def _run_child(self) -> None:
        import pytest

        # A prior child may have compiled and cached the guarded file's old
        # contents to disk (__pycache__ is real filesystem state, shared
        # across forks, not process-private). Without this, a subsequent
        # child can read back stale bytecode for a file that was mutated in
        # between — on filesystems with coarse mtime resolution this is not
        # just a test artifact, it is a real false-survivor risk.
        _invalidate_bytecode_cache(self._guarded_path)
        sys.dont_write_bytecode = True
        try:
            exit_code = _run_pytest_output_suppressed(pytest, self._extra_args, self._cwd)
        except BaseException:
            os._exit(3)
        os._exit(exit_code if isinstance(exit_code, int) else int(exit_code))


def _invalidate_bytecode_cache(guarded_path: str) -> None:
    """Remove any compiled-bytecode cache for guarded_path, if present."""
    try:
        cached = importlib.util.cache_from_source(guarded_path)
    except ValueError:
        return
    try:
        os.remove(cached)
    except FileNotFoundError:
        pass


def _run_pytest_output_suppressed(pytest_module, args: list[str], cwd: str) -> int:
    """Run pytest.main(args) with cwd set and stdout/stderr redirected to devnull."""
    prev_cwd = os.getcwd()
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved_stdout = os.dup(1)
    saved_stderr = os.dup(2)
    try:
        os.chdir(cwd)
        os.dup2(devnull_fd, 1)
        os.dup2(devnull_fd, 2)
        return int(pytest_module.main(args))
    finally:
        os.dup2(saved_stdout, 1)
        os.dup2(saved_stderr, 2)
        os.close(saved_stdout)
        os.close(saved_stderr)
        os.close(devnull_fd)
        os.chdir(prev_cwd)


def _wait_for_child(pid: int, timeout: float) -> tuple[str, bool]:
    deadline = time.monotonic() + timeout
    while True:
        done_pid, status = os.waitpid(pid, os.WNOHANG)
        if done_pid == pid:
            break
        if time.monotonic() >= deadline:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
            return "timeout", True
        time.sleep(_POLL_INTERVAL)
    if os.WIFSIGNALED(status):
        return "killed", False
    exit_code = os.WEXITSTATUS(status)
    return ("survived" if exit_code == 0 else "killed"), False
