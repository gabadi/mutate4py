"""Orchestrates --build-test-contexts: node-id collection then the isolated-
session db build. Extracted from `_runner.py` to keep that module under its
size cap (see `tach.toml`'s header comment on single-module extractions).
"""

import logging

from mutate4py._test_collection import TestCollectionError, collect_test_node_ids, isolated_run_pytest_args
from mutate4py._test_context_build import IsolatedSessionRunner, TestContextBuildError, build_test_context_db
from mutate4py._test_context_cache import build_cache, discard_cache, should_skip_rebuild, write_cache

__all__ = ["build_test_contexts"]

_logger = logging.getLogger(__name__)


def build_test_contexts(
    *,
    output_db_path: str,
    cwd: str,
    pytest_args: list[str],
    isolated_session_runner: IsolatedSessionRunner | None = None,
) -> int:
    """Execute --build-test-contexts: collect every test pytest would run
    (scoped by pytest_args), then build an isolated-session test-context db
    at output_db_path (see docs/adr/0021), unless a fresh cache proves
    nothing that would change it has changed since the last build (#52).
    Returns 0 on success (built or skipped), 1 if collection or the build
    fails.

    collect_test_node_ids always runs — it's the cheap collection pass, not
    a per-test coverage session, and its result is exactly what the
    freshness check needs. Only build_test_context_db (the expensive part:
    one isolated coverage.py session per test) is skipped on a cache hit.

    collect_test_node_ids gets the full pytest_args (a scoping path, if any,
    must reach it); build_test_context_db gets isolated_run_pytest_args'
    filtered version instead — a path token forwarded to a per-test isolated
    run would make pytest run every test under that path, not just the one
    node ID names (see isolated_run_pytest_args' docstring).

    isolated_session_runner is passed straight through to build_test_context_db
    (see its docstring) — None keeps the existing cold subprocess path.

    The cache is discarded before the build and rewritten after it, so a
    build that fails partway through leaves no cache vouching for the db it
    was overwriting.
    """
    try:
        node_ids = collect_test_node_ids(cwd=cwd, pytest_args=pytest_args)
    except TestCollectionError as exc:
        _logger.error(f"error: {exc}")
        return 1

    if should_skip_rebuild(output_db_path=output_db_path, node_ids=node_ids, cwd=cwd):
        _logger.info(f"Test-context db unchanged, skipping rebuild: {output_db_path}")
        return 0

    discard_cache(output_db_path)
    try:
        build_test_context_db(
            node_ids,
            cwd=cwd,
            output_db_path=output_db_path,
            pytest_args=isolated_run_pytest_args(pytest_args, cwd=cwd),
            isolated_session_runner=isolated_session_runner,
        )
    except TestContextBuildError as exc:
        _logger.error(f"error: {exc}")
        return 1

    write_cache(output_db_path, build_cache(node_ids, cwd=cwd, output_db_path=output_db_path))

    _logger.info(f"Test-context db written: {output_db_path} ({len(node_ids)} tests)")
    return 0
