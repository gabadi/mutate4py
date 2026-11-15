"""Unit tests for run-loop site selection (_site_selection.py)."""

from mutate4py._discovery import Site
from mutate4py._site_selection import (
    _is_differential,
    _select_sites,
    _should_run_parallel,
)
import pytest


# ── _select_sites ─────────────────────────────────────────────────────────────


def _make_site(index, line, fid="func/f") -> Site:
    return Site(
        index=index,
        line=line,
        col=0,
        end_line=line,
        end_col=5,
        function_id=fid,
        orig_text=">",
        mutant_text=">=",
        desc="> -> >=",
    )


@pytest.mark.unit
def test_select_sites_all_covered_non_differential():
    sites = [_make_site(0, 1, "func/f"), _make_site(1, 2, "func/g")]
    covered = {1, 2}
    _, selected = _select_sites(sites, covered, set(), differential=False)
    assert len(selected) == 2


@pytest.mark.unit
def test_select_sites_differential_filters_unchanged():
    sites = [_make_site(0, 1, "func/f"), _make_site(1, 2, "func/g")]
    covered = {1, 2}
    changed = {"func/f"}
    _, selected = _select_sites(sites, covered, changed, differential=True)
    assert len(selected) == 1
    assert selected[0].function_id == "func/f"


@pytest.mark.unit
def test_select_sites_uncovered_excluded():
    sites = [_make_site(0, 1, "func/f"), _make_site(1, 2, "func/g")]
    covered = {1}  # line 2 uncovered
    _, selected = _select_sites(sites, covered, set(), differential=False)
    assert len(selected) == 1
    assert selected[0].line == 1


@pytest.mark.unit
def test_select_sites_differential_keeps_covered_sites_of_changed_function_only():
    """Covered is every covered Site, but Selected narrows to the changed function's covered Sites."""
    sites = [_make_site(0, 1, "func/f"), _make_site(1, 2, "func/f"), _make_site(2, 3, "func/g")]
    covered_sites, selected = _select_sites(sites, {1, 3}, {"func/f"}, differential=True)
    assert [s.line for s in covered_sites] == [1, 3]
    assert [s.line for s in selected] == [1]


# ── _should_run_parallel boundary conditions ──────────────────────────────────


@pytest.mark.unit
def test_should_run_parallel_exact_boundary():
    """max_workers=2, n_selected=2 -> parallel (inclusive on both)."""
    assert _should_run_parallel(max_workers=2, n_selected=2) is True


@pytest.mark.unit
def test_should_run_parallel_one_worker():
    """max_workers=1 -> serial even with many sites."""
    assert _should_run_parallel(max_workers=1, n_selected=10) is False


@pytest.mark.unit
def test_should_run_parallel_one_site():
    """n_selected=1 -> serial even with many workers."""
    assert _should_run_parallel(max_workers=8, n_selected=1) is False


@pytest.mark.unit
def test_should_run_parallel_two_workers_one_site():
    """max_workers=2, n_selected=1 -> serial."""
    assert _should_run_parallel(max_workers=2, n_selected=1) is False


@pytest.mark.unit
def test_should_run_parallel_three_workers():
    """max_workers=3, n_selected=2 -> parallel."""
    assert _should_run_parallel(max_workers=3, n_selected=2) is True


# ── _is_differential: the Manifest alone decides ─────────────────────────────


@pytest.mark.unit
def test_is_differential_with_a_manifest():
    """A Manifest exists -> a differential rerun."""
    assert _is_differential(manifest_exists=True) is True


@pytest.mark.unit
def test_is_differential_no_manifest():
    """No Manifest -> a full-file run."""
    assert _is_differential(manifest_exists=False) is False
