"""Forking executor for the serial mutation loop.

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
`assert_source_clean` enforces this after priming; `ForkingExecutor.prime`
raises `ModuleLeakError` rather than silently proceeding unsafe.

Pytest is the supported runner by contract — there is no other execution
shape to sniff for, so priming never inspects the argument list it will
later be called with.
"""

import importlib.util
import os
import signal
import sys
import tempfile
import time
from typing import Callable

from mutate4py._cmd import classify_exit_code
from mutate4py._plugin_neutralisation import neutralising_args

__all__ = [
    "ForkingExecutor",
    "ForkingExecutorUnavailable",
    "ModuleLeakError",
    "assert_source_clean",
    "is_available",
    "isolated_coverage_session_safe",
]

_POLL_INTERVAL = 0.01

# pytest-tach's Rust extension spawns native threads during collection and
# holds a lock across pytest_configure; priming's own collect-only
# pytest.main() call triggers that once, and a *second* in-process
# pytest.main() call in a forked child then deadlocks forever trying to
# re-acquire it post-fork (classic native-lock-held-at-fork-time hazard —
# matches CPython's own fork()-in-multithreaded-process warning). Confirmed
# by hanging faulthandler.dump_traceback_later inside tach's Rust parser.
# `run()` (Mutant execution) never hits this in mutate4py's own dogfooding
# only by coincidence -- the target file being mutated is usually already
# self-imported, which routes it to the subprocess executor via
# assert_source_clean before any fork happens. `run_isolated_coverage_session`
# has no such file to leak-check (nothing is ever mutated), so it needs this
# explicit precheck instead.
_FORK_UNSAFE_PLUGIN_MODULES = ("tach.pytest_plugin",)


def isolated_coverage_session_safe() -> bool:
    """False if a plugin known to deadlock fork()-after-prime() (see module
    docstring above `_FORK_UNSAFE_PLUGIN_MODULES`) is already loaded in this
    process. Checked once per process, like all forking-executor eligibility
    (`_executor_selection.py`) -- a loaded plugin can't become safe mid-run,
    so callers should decide this before the first
    `run_isolated_coverage_session` call, not per node_id.
    """
    return not any(name in sys.modules for name in _FORK_UNSAFE_PLUGIN_MODULES)


class ForkingExecutorUnavailable(Exception):
    """Forking-executor preconditions are not met; caller should fall back."""


class ModuleLeakError(ForkingExecutorUnavailable):
    """The guarded target file is already present in sys.modules."""


def is_available() -> bool:
    """True if the platform supports the forking executor (POSIX os.fork)."""
    return hasattr(os, "fork")


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
            "the forking executor cannot guarantee children re-read the mutated file"
        )


class ForkingExecutor:
    """Primes pytest once for `cwd`, then forks a child per mutant.

    `guarded_path` must never be importable in this process before or
    between forks. Call `prime()` once; it raises `ForkingExecutorUnavailable`
    (including the narrower `ModuleLeakError`) if the fast path is not safe
    for this project, in which case the caller should fall back to the
    subprocess executor instead of calling `run()`.
    """

    def __init__(self, cwd: str, guarded_path: str) -> None:
        self._cwd = cwd
        self._guarded_path = guarded_path
        self._primed = False

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
        with tempfile.TemporaryDirectory(dir=scratch_root, prefix="prime-") as empty_dir:
            _run_pytest_output_suppressed(pytest, ["--collect-only", "-q", empty_dir, *neutralising_args()], self._cwd)

        assert_source_clean(self._guarded_path)
        self._primed = True

    def _fork_and_wait(self, child: Callable[[], None], timeout: float) -> str:
        """Fork, run `child` in the forked process, and classify how it ended.

        `child` never returns — every child entry point ends in os._exit —
        so the trailing exit is only there to make an escaped return fatal
        rather than let a second copy of the parent run on.
        """
        pid = os.fork()
        if pid == 0:
            child()
            os._exit(70)  # pragma: no cover - every child entry point calls os._exit
        return _wait_for_child(pid, timeout)

    def run(self, args: list[str], timeout: float) -> str:
        """Fork a child that runs pytest.main(args) once; return the classification."""
        if not self._primed:
            raise ForkingExecutorUnavailable("prime() must succeed before run()")
        return self._fork_and_wait(lambda: self._run_child(args), timeout)

    def run_isolated_coverage_session(
        self, node_id: str, *, data_file: str, pytest_args: list[str], timeout: float
    ) -> str:
        """Fork a child that runs exactly node_id under a coverage.py session
        statically named `context=node_id`, saving to `data_file` — the warm
        equivalent of `coverage run --context=<node_id> --data-file=<data_file>
        -m pytest <node_id>` (see _test_context_build.py / ADR 0021), minus
        the per-process interpreter/plugin-bootstrap cost `run()` already
        avoids for Mutant execution. Returns the same classification
        vocabulary as `run()` (survived/killed/timeout/no-tests-collected/
        usage-error); the caller decides what "not survived" means for it.

        Nothing is ever mutated on disk between calls here (unlike `run()`,
        which exists to re-read a just-mutated file post-fork), so there is
        no bytecode-cache-invalidation step: whatever the child reads for
        node_id's own file is, by construction, the only content it will
        ever have during this build.
        """
        if not self._primed:
            raise ForkingExecutorUnavailable("prime() must succeed before run_isolated_coverage_session()")
        if not isolated_coverage_session_safe():
            raise ForkingExecutorUnavailable(
                "a fork-unsafe pytest plugin is loaded (see _FORK_UNSAFE_PLUGIN_MODULES); "
                "the caller must fall back to the subprocess executor"
            )
        return self._fork_and_wait(
            lambda: self._run_coverage_child(node_id, data_file=data_file, pytest_args=pytest_args), timeout
        )

    def _run_child(self, args: list[str]) -> None:
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
            exit_code = _run_pytest_output_suppressed(pytest, args, self._cwd)
        except BaseException:
            os._exit(3)
        os._exit(exit_code if isinstance(exit_code, int) else int(exit_code))

    def _run_coverage_child(self, node_id: str, *, data_file: str, pytest_args: list[str]) -> None:
        import coverage
        import pytest

        sys.dont_write_bytecode = True
        try:
            # cwd must be set before Coverage() is constructed: coverage.py
            # auto-discovers its config (pyproject.toml/.coveragerc) from the
            # current working directory at construction time, and this
            # process's cwd is still wherever the parent last left it until
            # _run_pytest_output_suppressed's own chdir — which runs too
            # late, after config discovery would already have happened.
            os.chdir(self._cwd)
            cov = coverage.Coverage(data_file=data_file, context=node_id)
            cov.start()
            try:
                exit_code = _run_pytest_output_suppressed(pytest, [node_id, *pytest_args], self._cwd)
            finally:
                cov.stop()
                cov.save()
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
    """Run pytest.main(args) with cwd set and stdout/stderr redirected to devnull.

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
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved_stdout = os.dup(1)
    saved_stderr = os.dup(2)
    try:
        os.chdir(cwd)
        os.dup2(devnull_fd, 1)
        os.dup2(devnull_fd, 2)
        return int(pytest_module.main(args))
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved_stdout, 1)
        os.dup2(saved_stderr, 2)
        os.close(saved_stdout)
        os.close(saved_stderr)
        os.close(devnull_fd)
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
