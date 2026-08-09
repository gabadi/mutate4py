"""Run-loop pre-flight setup: opening the test-context db (which forces
serial execution when active) and priming a `ForkServer` as a best-effort
accelerator ahead of the per-mutant loop. Neither step ever raises on its
own account — an unavailable fork server falls back to the per-mutant
subprocess model instead of failing the run.
"""

import logging
import shlex

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


def _prepare_fork_server(*, requested: bool, test_command: str, cwd: str, guarded_path: str):
    """Build and prime a ForkServer for the serial loop, or None to keep the
    existing per-mutant subprocess model.

    Never raises: any unavailability or priming failure (wrong platform,
    test_command isn't a plain `pytest` invocation, pytest not importable in
    this process, or the target leaking into sys.modules during priming) is
    reported and treated as "fall back", never as a hard error — the fork
    server is a best-effort accelerator, on by default, not a
    correctness-affecting choice, so it degrades silently to the slower but
    always-correct subprocess model wherever it isn't safe or applicable.
    """
    if not requested:
        return None
    from mutate4py._fork_server import ForkServer, ForkServerUnavailable, is_available

    if not is_available(test_command):
        _logger.info(
            "note: fork-server fast path needs a plain `pytest` --test-command "
            "on a POSIX platform; using the per-mutant subprocess model instead."
        )
        return None
    extra_args = shlex.split(test_command)[1:]
    server = ForkServer(cwd=cwd, extra_args=extra_args, guarded_path=guarded_path)
    try:
        server.prime()
    except ForkServerUnavailable as exc:
        _logger.info(f"note: fork-server fast path unavailable ({exc}); using the per-mutant subprocess model instead.")
        return None
    return server


def _fork_server_eligible(
    *,
    fork_server_requested: bool,
    use_parallel: bool,
    test_ctx_db,
    selected_sites: list,
) -> bool:
    """Whether the fork-server fast path may be attempted for this run.

    Mutually exclusive with parallel workers and per-mutant test-context
    narrowing: ForkServer.run always executes the full test_command with no
    per-site command variation, so it cannot honor either.
    """
    return fork_server_requested and not use_parallel and test_ctx_db is None and bool(selected_sites)
