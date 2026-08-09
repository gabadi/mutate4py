"""Site selection for the run loop: coverage acquisition, since-last-run/lines-filter
narrowing of which sites get mutated, and the serial/parallel switch.
"""

import logging

from mutate4py._coverage import CoverageError, acquire_coverage
from mutate4py._discovery import Site
from mutate4py._report import _uncovered_block_lines

_logger = logging.getLogger(__name__)


def _filter_by_lines(covered: list[Site], lines_filter: set[int]) -> list[Site]:
    return [s for s in covered if s.line in lines_filter]


def _filter_by_fn(covered: list[Site], changed_fn_ids: set[str]) -> list[Site]:
    return [s for s in covered if s.function_id in changed_fn_ids]


def _select_sites(
    all_sites: list[Site],
    covered_lines: set[int],
    changed_fn_ids: set[str],
    *,
    effective_since_last_run: bool,
    lines_filter: set[int] | None,
) -> tuple[list[Site], list[Site]]:
    """Return (covered_sites, selected_sites)."""
    covered = [s for s in all_sites if s.line in covered_lines]
    if lines_filter is not None:
        return covered, _filter_by_lines(covered, lines_filter)
    if effective_since_last_run:
        return covered, _filter_by_fn(covered, changed_fn_ids)
    return covered, covered


def _acquire_covered_lines(
    cov_cmd: str | None,
    lcov_path: str | None,
    *,
    reuse_coverage: bool,
    cwd: str,
    abs_source: str,
) -> tuple[set[int] | None, str | None]:
    """Acquire coverage; return (covered_lines, error_message_or_None)."""
    if reuse_coverage:
        _logger.info("Reusing existing coverage; covered/uncovered classification may be stale.")
    try:
        covered_lines = acquire_coverage(
            cov_cmd=cov_cmd,
            lcov_path=lcov_path,
            reuse=reuse_coverage,
            cwd=cwd,
            source_path=abs_source,
        )
        return covered_lines, None
    except CoverageError as exc:
        return None, str(exc)


def _is_effective_since_last_run(
    *,
    since_last_run: bool,
    manifest_exists: bool,
    mutate_all: bool,
    lines_filter: set[int] | None,
) -> bool:
    return since_last_run or (manifest_exists and not mutate_all and lines_filter is None)


def _should_run_parallel(max_workers: int, n_selected: int) -> bool:
    return max_workers >= 2 and n_selected >= 2


def _uncovered_lines_if_needed(
    all_sites: list[Site],
    covered_lines: set[int],
    *,
    effective_since_last_run: bool,
    lines_filter: set[int] | None,
) -> list[str]:
    """Return the uncovered-sites report block's lines, or [] when it doesn't apply.

    Returns rather than prints — unlike `_runner.py`, this module isn't the run
    loop's edge, so the caller (`_select_and_prepare`) is responsible for the
    single `_print_lines` call, same as every other report block it prints.
    """
    if not effective_since_last_run and lines_filter is None:
        return _uncovered_block_lines(all_sites, covered_lines)
    return []
