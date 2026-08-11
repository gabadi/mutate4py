"""Orchestrates --build-test-contexts: node-id collection then the isolated-
session db build. Extracted from `_runner.py` to keep that module under its
size cap (see `tach.toml`'s header comment on single-module extractions).
"""

import logging

from mutate4py._test_collection import TestCollectionError, collect_test_node_ids, isolated_run_pytest_args
from mutate4py._test_context_build import TestContextBuildError, build_test_context_db

__all__ = ["build_test_contexts"]

_logger = logging.getLogger(__name__)


def build_test_contexts(*, output_db_path: str, cwd: str, pytest_args: list[str]) -> int:
    """Execute --build-test-contexts: collect every test pytest would run
    (scoped by pytest_args), then build an isolated-session test-context db
    at output_db_path (see docs/adr/0021). Returns 0 on success, 1 if
    collection or the build fails.

    The single call site below (collect_test_node_ids -> build_test_context_db)
    is deliberately the only place either step runs, so a future cache check
    (#52) has one clear point to intercept before either starts.

    collect_test_node_ids gets the full pytest_args (a scoping path, if any,
    must reach it); build_test_context_db gets isolated_run_pytest_args'
    filtered version instead — a path token forwarded to a per-test isolated
    run would make pytest run every test under that path, not just the one
    node ID names (see isolated_run_pytest_args' docstring).
    """
    try:
        node_ids = collect_test_node_ids(cwd=cwd, pytest_args=pytest_args)
    except TestCollectionError as exc:
        _logger.error(f"error: {exc}")
        return 1
    try:
        build_test_context_db(
            node_ids,
            cwd=cwd,
            output_db_path=output_db_path,
            pytest_args=isolated_run_pytest_args(pytest_args, cwd=cwd),
        )
    except TestContextBuildError as exc:
        _logger.error(f"error: {exc}")
        return 1
    _logger.info(f"Test-context db written: {output_db_path} ({len(node_ids)} tests)")
    return 0
