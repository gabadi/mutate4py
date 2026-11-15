"""Site selection for the run loop: differential narrowing of which sites get
mutated (only the Sites of changed functions once a Manifest exists), and the
serial/parallel switch.
"""

from mutate4py._discovery import Site
from mutate4py._report import _uncovered_block_lines


def _filter_by_fn(covered: list[Site], changed_fn_ids: set[str]) -> list[Site]:
    return [s for s in covered if s.function_id in changed_fn_ids]


def _select_sites(
    all_sites: list[Site],
    covered_lines: set[int],
    changed_fn_ids: set[str],
    *,
    differential: bool,
) -> tuple[list[Site], list[Site]]:
    """Return (covered_sites, selected_sites)."""
    covered = [s for s in all_sites if s.line in covered_lines]
    if differential:
        return covered, _filter_by_fn(covered, changed_fn_ids)
    return covered, covered


def _is_differential(*, manifest_exists: bool) -> bool:
    """A differential rerun (CONTEXT.md): a Manifest exists. A run with no Manifest is a full-file run."""
    return manifest_exists


def _should_run_parallel(max_workers: int, n_selected: int) -> bool:
    return max_workers >= 2 and n_selected >= 2


def _uncovered_lines_if_needed(
    all_sites: list[Site],
    covered_lines: set[int],
    *,
    differential: bool,
) -> list[str]:
    """Return the uncovered-sites report block's lines, or [] when it doesn't apply.

    Returns rather than prints — unlike `_runner.py`, this module isn't the run
    loop's edge, so the caller (`_select_and_prepare`) is responsible for the
    single `_print_lines` call, same as every other report block it prints.
    """
    if not differential:
        return _uncovered_block_lines(all_sites, covered_lines)
    return []
