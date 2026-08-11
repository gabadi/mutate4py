"""Per-Mutant test-selection dispatch: builds the pytest argument list for
one Site given its Selection outcome.

Shared by both execution paths — the serial loop (`_execution.py`) and
parallel Workers (`_workers.py`) — which is why it sits in the domain layer
rather than in either caller. See tach.toml before moving it.
"""

from mutate4py._discovery import Site

__all__ = ["TestSelectionError", "_build_mutant_args"]


class TestSelectionError(Exception):
    """A selected site the test-context db cannot account for (case 3)."""


# The selected sites are LCOV-covered by construction, so a miss is always an
# input defect, never uncovered code — hence a hard error rather than a fallback.
_DISAGREEMENT_HINTS = {
    "line-absent": "line is LCOV-covered but absent from the test-context db "
    "(stale db: regenerate it with pytest --cov-context=test)",
    "file-absent": "file is not in the test-context db at all "
    "(path-format mismatch, or its coverage was recorded in a subprocess)",
}


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
