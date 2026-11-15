"""Site selection for the run loop: differential narrowing of which sites get
mutated (only the Sites of changed functions once a Manifest exists), and the
serial/parallel switch.
"""

from mutate4py._discovery import Site


def _filter_by_fn(covered: list[Site], changed_fn_ids: set[str]) -> list[Site]:
    return [s for s in covered if s.function_id in changed_fn_ids]


def _sites_in_run_scope(
    all_sites: list[Site],
    changed_fn_ids: set[str],
    *,
    differential: bool,
) -> list[Site]:
    if differential:
        return _filter_by_fn(all_sites, changed_fn_ids)
    return all_sites


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


def _should_run_parallel(max_workers: int, n_selected: int) -> bool:
    return max_workers >= 2 and n_selected >= 2
