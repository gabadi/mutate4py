"""Executor selection (issue 04b): the forking executor when requested and
eligible for this process, the subprocess executor otherwise.

Eligibility is a property of *this interpreter's* import state (module-leak
detection), not of the run as a whole, so the choice is made once per
process attempting it — the serial run loop's own process for a run with a
single Worker, or a Worker subprocess's own process for a parallel run
(`_worker_server.py`). Both callers sit above `execution_backends`, so this
module lives at that layer rather than in either one's own module.
"""

import logging

from mutate4py._executor import Executor

_logger = logging.getLogger(__name__)

__all__ = ["_prepare_executor", "select_executor"]


def select_executor(
    *, caller_supplied: Executor | None, use_parallel: bool, requested: bool, cwd: str, guarded_path: str
) -> Executor | None:
    """Pick the executor for a run: the caller-supplied one when given (used
    as-is, never re-primed here — the caller owns priming, e.g. a fake
    executor in tests or one already primed by a longer-lived caller); None
    when a parallel run defers priming to each Worker's own process (issue
    04b); a freshly prepared one otherwise.
    """
    if caller_supplied is not None:
        return caller_supplied
    if use_parallel:
        return None
    return _prepare_executor(requested=requested, cwd=cwd, guarded_path=guarded_path)


def _prepare_executor(*, requested: bool, cwd: str, guarded_path: str) -> Executor:
    """Return a primed Executor: the forking executor when requested and
    eligible, the subprocess executor otherwise.

    Never raises: any unavailability or priming failure (wrong platform,
    pytest not importable in this process, or the target leaking into
    sys.modules during priming) is reported and treated as "fall back",
    never as a hard error — the forking executor is a best-effort
    accelerator, on by default, not a correctness-affecting choice, so it
    degrades silently to the slower but always-correct subprocess executor
    wherever it isn't safe or applicable.
    """
    if requested:
        from mutate4py._forking_executor import ForkingExecutor, ForkingExecutorUnavailable, is_available

        if not is_available():
            _logger.info("note: the forking executor needs a POSIX platform; using the subprocess executor instead.")
        else:
            executor = ForkingExecutor(cwd=cwd, guarded_path=guarded_path)
            try:
                executor.prime()
                return executor
            except ForkingExecutorUnavailable as exc:
                _logger.info(f"note: forking executor unavailable ({exc}); using the subprocess executor instead.")

    from mutate4py._subprocess_executor import SubprocessExecutor

    executor = SubprocessExecutor(cwd=cwd)
    executor.prime()
    return executor
