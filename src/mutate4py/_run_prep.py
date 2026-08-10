"""Run-loop pre-flight setup: opening the test-context db (which forces
serial execution when active) and preparing this run's executor — the
forking fast path when eligible and available, the subprocess executor
otherwise. Executor preparation never raises on its own account — an
unavailable or failed-priming forking executor falls back to the
subprocess executor instead of failing the run.
"""

import logging

from mutate4py._executor import Executor

_logger = logging.getLogger(__name__)


def _setup_test_context_db(test_contexts_path: str | None, max_workers: int):
    """Open the test-context db if requested; force serial execution when doing so.

    Returns (test_ctx_db_or_None, effective_max_workers).
    """
    if test_contexts_path is None:
        return None, max_workers
    from mutate4py._test_selection import TestContextDB

    test_ctx_db = TestContextDB(test_contexts_path)
    effective_max_workers = 0 if max_workers >= 2 else max_workers
    return test_ctx_db, effective_max_workers


def _prepare_executor(*, requested: bool, cwd: str, guarded_path: str) -> Executor:
    """Return a primed Executor for the serial loop: the forking executor when
    requested and eligible, the subprocess executor otherwise.

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


def _forking_eligible(
    *,
    forking_requested: bool,
    use_parallel: bool,
    test_ctx_db,
    selected_sites: list,
) -> bool:
    """Whether the forking executor may be attempted for this run.

    Mutually exclusive with parallel workers and per-mutant test-context
    narrowing: the forking executor always runs pytest against one fixed
    argument list per mutant, so it cannot honor per-site narrowing here.
    """
    return forking_requested and not use_parallel and test_ctx_db is None and bool(selected_sites)
