"""Executor selection: the forking executor when requested and
eligible for this process, the subprocess executor otherwise.

Eligibility is a property of *this interpreter* (its platform, its pytest,
the plugins its prime session registers), so the choice is made once per
process attempting it: a Worker server's own process (`_worker_server.py`),
whether it is one Worker of a parallel run or the fork server a serial run
starts over the project tree. The orchestrator itself never primes a forking
executor. See tach.toml for why this module may not sit in a layer above
`execution_backends`.
"""

import logging
from collections.abc import Sequence

from mutate4py._executor import Executor
from mutate4py._plugin_neutralisation import disabled_plugin_args

_logger = logging.getLogger(__name__)

__all__ = ["_prepare_executor", "select_executor"]


def select_executor(
    *,
    use_parallel: bool,
    no_fork_reason: str | None,
    cwd: str,
    guarded_path: str,
    pytest_args: Sequence[str] = (),
    ran_at_import: frozenset[int] = frozenset(),
) -> Executor | None:
    """Pick the executor for a run the caller supplied none for: None when a
    parallel run defers priming to each Worker's own process (issue 04b); a
    primed fork server when the forking executor is wanted and this platform
    can fork; a primed subprocess executor otherwise. no_fork_reason is None
    when the forking executor is wanted; otherwise it is the reason the
    subprocess executor reports for not forking. The fork server primes with
    the run's own `-p no:<name>` blocks from pytest_args; ran_at_import are the
    guarded file's lines the Measurement saw run at import (swap mode refuses them).
    """
    if use_parallel:
        return None
    if no_fork_reason is None and _can_fork():
        return _primed_fork_server(cwd, guarded_path, pytest_args, ran_at_import)
    return _prepare_executor(
        requested=no_fork_reason is None, cwd=cwd, guarded_path=guarded_path, no_fork_reason=no_fork_reason or ""
    )


def _can_fork() -> bool:
    from mutate4py._forking_executor import is_available

    return is_available()


def _primed_fork_server(
    cwd: str, guarded_path: str, pytest_args: Sequence[str], ran_at_import: frozenset[int]
) -> Executor:
    from mutate4py._worker_protocol import fork_server

    server = fork_server(
        cwd=cwd,
        guarded_path=guarded_path,
        prime_args=disabled_plugin_args(list(pytest_args)),
        ran_at_import=ran_at_import,
    )
    server.prime()
    return server


def _prepare_executor(
    *,
    requested: bool,
    cwd: str,
    guarded_path: str,
    no_fork_reason: str = "--no-fork",
    prime_args: Sequence[str] = (),
    ran_at_import: frozenset[int] = frozenset(),
) -> Executor:
    """Return a primed Executor: the forking executor when requested and
    eligible, the subprocess executor otherwise.

    Never raises: any unavailability or priming failure (wrong platform,
    pytest not importable in this process, or a fork-unsafe plugin in the
    prime session) is reported, through the subprocess executor's reason, and
    treated as "fall back", never as a hard error.
    """
    reason = no_fork_reason
    if requested:
        from mutate4py._forking_executor import ForkingExecutor, ForkingExecutorUnavailable, is_available

        if not is_available():
            reason = "the forking executor needs a POSIX platform"
            _logger.info("note: the forking executor needs a POSIX platform; using the subprocess executor instead.")
        else:
            executor = ForkingExecutor(
                cwd=cwd, guarded_path=guarded_path, prime_args=prime_args, ran_at_import=ran_at_import
            )
            try:
                executor.prime()
                return executor
            except ForkingExecutorUnavailable as exc:
                reason = exc.reason
                _logger.info(f"note: {reason}; using the subprocess executor instead.")

    from mutate4py._subprocess_executor import SubprocessExecutor

    executor = SubprocessExecutor(cwd=cwd, guarded_path=guarded_path, reason=reason)
    executor.prime()
    return executor
