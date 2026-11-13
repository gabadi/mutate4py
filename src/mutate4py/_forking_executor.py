"""Forking executor, primed inside a Worker server: the fork server a serial
run starts over the project tree, or one Worker of a parallel run. The
orchestrator never primes one itself (`_executor_selection.select_executor`).

A parent process primes pytest/plugins/framework setup once (running a
collect-only pass against an empty directory, so root conftest.py and
framework bootstrap — e.g. django.setup() — run without importing any real
test file), then fork()s a child per mutant. POSIX-only (requires os.fork).

A fork inherits the parent's sys.modules, so `prime` decides once, per guarded
file, how each child gets the mutated code (`file_mode`):

- **fresh import**: the guarded file is not loaded after prime. Each child
  calls pytest.main() in-process and imports the file fresh from its current
  (mutated) on-disk contents.
- **harness**: the guarded file is one of this process's own modules, loaded
  before prime (the executor and protocol code the child runs around pytest).
  Mutated code there could rewrite the child's own result into a false kill or
  a false Survivor, so every Mutant runs in a fresh interpreter.
- **loaded**: prime imported the guarded file (a conftest or a plugin did), so
  the child's copy is the clean one: every Mutant runs in a fresh interpreter.

A fresh interpreter is the forked child exec()ing `python -m pytest`: the pid
stays the same, so the parent's wait, timeout kill and exit-code
Classification are unchanged.

Pytest is the supported runner by contract — there is no other execution
shape to sniff for, so priming never inspects the argument list it will
later be called with.
"""

import contextlib
import os
import signal
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from typing import Callable

from mutate4py._bytecode_cache import invalidate_bytecode_cache
from mutate4py._cmd import classify_exit_code
from mutate4py._executor import ExecutorDescription
from mutate4py._plugin_neutralisation import neutralising_args

__all__ = [
    "ForkUnsafePlugin",
    "ForkingExecutor",
    "ForkingExecutorUnavailable",
    "file_mode",
    "fork_unsafe_plugins",
    "fresh_interpreter_argv",
    "fresh_interpreter_env",
    "is_available",
]

_POLL_INTERVAL = 0.01

# pytest-tach's Rust extension spawns native threads during collection and
# holds a lock across pytest_configure; priming's own collect-only
# pytest.main() call triggers that once, and a *second* in-process
# pytest.main() call in a forked child then deadlocks forever trying to
# re-acquire it post-fork (classic native-lock-held-at-fork-time hazard —
# matches CPython's own fork()-in-multithreaded-process warning). Confirmed
# by hanging faulthandler.dump_traceback_later inside tach's Rust parser.
_FORK_UNSAFE_PLUGIN_MODULES = ("tach.pytest_plugin",)


def fork_unsafe_plugins(plugin_module_names: Sequence[str]) -> list[str]:
    """The plugins, among the module names a pytest session registered, known
    to deadlock a fork()-after-prime() (see `_FORK_UNSAFE_PLUGIN_MODULES`)."""
    return [name for name in _FORK_UNSAFE_PLUGIN_MODULES if name in plugin_module_names]


class ForkingExecutorUnavailable(Exception):
    """Forking-executor preconditions are not met; caller should fall back."""

    @property
    def reason(self) -> str:
        """Why the run falls back, as the subprocess executor reports it."""
        return f"forking executor unavailable: {self}"


class ForkUnsafePlugin(ForkingExecutorUnavailable):
    """The run's pytest session loads a plugin that deadlocks a forked child."""

    def __init__(self, plugins: Sequence[str]) -> None:
        super().__init__(f"fork-unsafe plugin: {', '.join(plugins)}")

    @property
    def reason(self) -> str:
        return str(self)


def is_available() -> bool:
    """True if the platform supports the forking executor (POSIX os.fork)."""
    return hasattr(os, "fork")


def _loaded_files() -> set[str]:
    """The real path of every module file this process has imported."""
    files = set()
    for mod in list(sys.modules.values()):
        mod_file = getattr(mod, "__file__", None)
        if mod_file:
            files.add(os.path.realpath(mod_file))
    return files


def file_mode(guarded_path: str, *, harness_files: set[str], loaded_after_prime: set[str]) -> str:
    """How each child gets the guarded file's mutated code: "harness" when it is
    one of the process's own modules from before prime, "loaded" when prime
    imported it, "fresh import" otherwise. Both sets hold real paths."""
    real = os.path.realpath(guarded_path)
    if real in harness_files:
        return "harness"
    if real in loaded_after_prime:
        return "loaded"
    return "fresh import"


class _PluginRecorder:
    """A pytest plugin that records the module name of every plugin its session registered."""

    def __init__(self) -> None:
        self.module_names: list[str] = []

    def pytest_configure(self, config) -> None:
        self.module_names = [getattr(p, "__name__", "") for p in config.pluginmanager.get_plugins()]


class ForkingExecutor:
    """Primes pytest once for `cwd`, then forks a child per mutant.

    Call `prime()` once; it raises `ForkingExecutorUnavailable` (including the
    narrower `ForkUnsafePlugin`) if the fast path is not safe for this
    project, in which case the caller should fall back to the subprocess
    executor instead of calling `run()`.
    """

    def __init__(self, cwd: str, guarded_path: str, prime_args: Sequence[str] = ()) -> None:
        self._cwd = cwd
        self._guarded_path = guarded_path
        self._prime_args = list(prime_args)
        self._mode: str | None = None
        self._fresh_imports = 0
        self._fresh_interpreters = 0

    def describe(self) -> ExecutorDescription:
        return ExecutorDescription(
            mode="forking", fresh_import=self._fresh_imports, fresh_interpreter=self._fresh_interpreters
        )

    def prime(self) -> None:
        try:
            import pytest
        except ImportError as exc:
            raise ForkingExecutorUnavailable(f"pytest is not importable in this process: {exc}") from exc

        # Must live inside cwd (not system tmp): pytest's conftest.py
        # discovery walks from rootdir down to each collected path, so an
        # empty dir outside the project tree would never see the project's
        # own conftest.py (and whatever framework bootstrap it runs) at all
        # — defeating the whole point of priming.
        scratch_root = os.path.join(self._cwd, ".mutate4py", "forkserver")
        os.makedirs(scratch_root, exist_ok=True)
        # neutralising_args() matters here too, not just on the per-Mutant
        # args in _runner.py: this call is itself an in-process, pre-fork
        # pytest.main() re-entry, so a target project's own addopts (e.g.
        # `--cov=...`) would otherwise spin up a second pytest-cov Coverage
        # instance inside the same interpreter that is running this
        # process's own coverage measurement — corrupting sys.monitoring's
        # already-armed line/branch tracking for the rest of the run.
        # prime_args (the run's own `-p no:<name>` blocks) keep a plugin the
        # run disables out of the process every child forks from.
        harness_files = _loaded_files()
        recorder = _PluginRecorder()
        with tempfile.TemporaryDirectory(dir=scratch_root, prefix="prime-") as empty_dir:
            collect_only = ["--collect-only", "-q", empty_dir, *neutralising_args(), *self._prime_args]
            _run_pytest_output_suppressed(pytest, collect_only, self._cwd, plugins=[recorder])

        unsafe = fork_unsafe_plugins(recorder.module_names)
        if unsafe:
            raise ForkUnsafePlugin(unsafe)
        self._mode = file_mode(self._guarded_path, harness_files=harness_files, loaded_after_prime=_loaded_files())

    def _fork_and_wait(self, child: Callable[[], None], timeout: float) -> str:
        """Fork, run `child` in the forked process, and classify how it ended.

        `child` never returns — every child entry point ends in os._exit or
        an exec — so the trailing exit is only there to make an escaped
        return fatal rather than let a second copy of the parent run on.
        """
        pid = os.fork()
        if pid == 0:
            child()
            os._exit(70)  # pragma: no cover - every child entry point calls os._exit
        return _wait_for_child(pid, timeout)

    def run(self, args: list[str], timeout: float) -> str:
        """Fork a child that runs pytest once over args; return the classification."""
        if self._mode is None:
            raise ForkingExecutorUnavailable("prime() must succeed before run()")
        if self._mode == "fresh import":
            self._fresh_imports += 1
            return self._fork_and_wait(lambda: self._run_child(args), timeout)
        self._fresh_interpreters += 1
        return self._fork_and_wait(lambda: self._exec_fresh_interpreter(args), timeout)

    def _exec_fresh_interpreter(self, args: list[str]) -> None:
        """Replace this child with this interpreter's `python -m pytest args`, as
        the subprocess executor runs it, output suppressed. Never returns."""
        try:
            invalidate_bytecode_cache(self._guarded_path)
            os.chdir(self._cwd)
            _silence_std_fds()
            os.execve(sys.executable, fresh_interpreter_argv(args), fresh_interpreter_env(os.environ))
        except BaseException:
            os._exit(3)

    def _run_child(self, args: list[str]) -> None:
        import pytest

        # A prior child may have compiled and cached the guarded file's old
        # contents to disk (__pycache__ is real filesystem state, shared
        # across forks, not process-private). Without this, a subsequent
        # child can read back stale bytecode for a file that was mutated in
        # between — on filesystems with coarse mtime resolution this is not
        # just a test artifact, it is a real false-survivor risk.
        invalidate_bytecode_cache(self._guarded_path)
        sys.dont_write_bytecode = True
        try:
            exit_code = _run_pytest_output_suppressed(pytest, args, self._cwd)
        except BaseException:
            os._exit(3)
        os._exit(exit_code if isinstance(exit_code, int) else int(exit_code))


def fresh_interpreter_argv(args: Sequence[str]) -> list[str]:
    """The argv a fresh-interpreter child execs: this interpreter's pytest over args.
    `-m` puts the child's cwd on sys.path, as for any `python -m pytest` (#82)."""
    return [sys.executable, "-m", "pytest", *args]


def fresh_interpreter_env(environ: Mapping[str, str]) -> dict[str, str]:
    """environ with bytecode writes off, as the subprocess executor runs pytest (#81)."""
    return {**environ, "PYTHONDONTWRITEBYTECODE": "1"}


def _silence_std_fds() -> None:
    """Point fds 0-2 at devnull: a Worker server's stdin and stdout are its protocol pipes."""
    devnull_fd = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(devnull_fd, fd)


def _run_pytest_output_suppressed(pytest_module, args: list[str], cwd: str, plugins: Sequence[object] = ()) -> int:
    """Run pytest.main(args, plugins) with cwd set and stdout/stderr redirected to devnull.

    cwd is on sys.path[0] for the call, as `python -m pytest` would put it (#82).

    Flushes sys.stdout/sys.stderr before restoring the real fds: Python's
    TextIOWrapper buffers writes at the object level, independent of the fd
    they currently point at, so an unflushed pytest summary line written
    while fd 1/2 point at devnull would otherwise surface later — after
    restoration — once something finally flushes it, leaking onto whatever
    now owns fd 1/2. Harmless for a human-readable terminal, but the
    Worker protocol treats every stdout line as a JSON message, so a leaked
    line there is a framing error, not just noise.
    """
    prev_cwd = os.getcwd()
    import_root = os.path.abspath(cwd)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved_stdout = os.dup(1)
    saved_stderr = os.dup(2)
    inserted = False
    try:
        os.chdir(cwd)
        sys.path.insert(0, import_root)
        inserted = True
        os.dup2(devnull_fd, 1)
        os.dup2(devnull_fd, 2)
        return int(pytest_module.main(args, plugins=list(plugins)))
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved_stdout, 1)
        os.dup2(saved_stderr, 2)
        os.close(saved_stdout)
        os.close(saved_stderr)
        os.close(devnull_fd)
        if inserted:
            with contextlib.suppress(ValueError):
                sys.path.remove(import_root)
        os.chdir(prev_cwd)


def _wait_for_child(pid: int, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    while True:
        done_pid, status = os.waitpid(pid, os.WNOHANG)
        if done_pid == pid:
            break
        if time.monotonic() >= deadline:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
            return "timeout"
        time.sleep(_POLL_INTERVAL)
    if os.WIFSIGNALED(status):
        return "killed"
    return classify_exit_code(os.WEXITSTATUS(status))
