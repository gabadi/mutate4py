"""Per-Mutant test-selection dispatch: builds the pytest argument list for
one Site given its Selection outcome.

Shared by both execution paths — the serial loop (`_execution.py`) and
parallel Workers (`_workers.py`) — which is why it sits in the domain layer
rather than in either caller. See tach.toml before moving it.
"""

import logging

from mutate4py._discovery import Site

__all__ = [
    "NoTestsCollectedError",
    "TestSelectionError",
    "_build_mutant_args",
    "_check_execution_status",
    "_log_dispatch_abort",
]

_logger = logging.getLogger(__name__)


class TestSelectionError(Exception):
    """A selected site the test-context db cannot account for (case 3)."""


class NoTestsCollectedError(Exception):
    """A selected site whose test run exercised no test at all (case 4)."""


# The selected sites are LCOV-covered by construction, so a miss is always an
# input defect, never uncovered code — hence a hard error rather than a fallback.
_DISAGREEMENT_HINTS = {
    "line-absent": "line is LCOV-covered but absent from the test-context db "
    "(stale db: regenerate it with pytest --cov-context=test)",
    "file-absent": "file is not in the test-context db at all "
    "(path-format mismatch, or its coverage was recorded in a subprocess)",
}

# Same shape as _DISAGREEMENT_HINTS, one step later: the db accounted for the
# line and named tests, but pytest ran none of them for this Mutant, so the
# exit code itself — not the db — is the input defect being reported.
_ABORT_HINTS = {
    "no-tests-collected": "pytest collected no tests to run (exit 5): a stale "
    "test-context db, a --pytest-args filter, or a node-ID path mismatch deselected everything",
    "usage-error": "pytest exited with a usage error before collecting any test (exit 4): "
    "check --pytest-args, or a stale test-context db naming a since-renamed/deleted test",
}


def _check_execution_status(status: str, abs_source_path: str, site: Site) -> None:
    """Raise NoTestsCollectedError if status means pytest ran no test at all for site."""
    hint = _ABORT_HINTS.get(status)
    if hint is not None:
        raise NoTestsCollectedError(f"{abs_source_path}:{site.line}: {hint}")


def _log_dispatch_abort(exc: TestSelectionError | NoTestsCollectedError) -> int:
    """Log a case-3 (db disagreement) or case-4 (no test ran) abort; both exit 2."""
    if isinstance(exc, TestSelectionError):
        _logger.error(f"error: test-context db disagrees with coverage: {exc}")
    else:
        _logger.error(f"error: pytest ran no test for a Mutant: {exc}")
    return 2


def _build_mutant_args(
    pytest_args: list[str], test_ctx_db, abs_source_path: str, site: Site
) -> tuple[list[str], str | None]:
    """Return (args, selection) for site; selection is None without a context db.

    "narrowed" runs only the tests covering site.line; "static" runs the full
    pytest_args because the line executes at import time and no test owns it.
    """
    if test_ctx_db is None:
        return pytest_args, None
    outcome, node_ids = test_ctx_db.tests_for_line(abs_source_path, site.line)
    if outcome == "narrowed":
        return [*pytest_args, *node_ids], "narrowed"
    if outcome == "static":
        return pytest_args, "static"
    # Every other outcome raises, so an unrecognized one can never fall through to
    # a full-suite run that the report would then miscount as narrowed.
    hint = _DISAGREEMENT_HINTS.get(outcome, f"unrecognized selection outcome {outcome!r}")
    raise TestSelectionError(f"{abs_source_path}:{site.line}: {hint}")
