"""Unit tests for run-loop site selection (_site_selection.py)."""

from mutate4py._discovery import Site
from mutate4py._site_selection import (
    _is_effective_since_last_run,
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
    _, selected = _select_sites(sites, covered, set(), effective_since_last_run=False, lines_filter=None)
    assert len(selected) == 2


@pytest.mark.unit
def test_select_sites_differential_filters_unchanged():
    sites = [_make_site(0, 1, "func/f"), _make_site(1, 2, "func/g")]
    covered = {1, 2}
    changed = {"func/f"}
    _, selected = _select_sites(sites, covered, changed, effective_since_last_run=True, lines_filter=None)
    assert len(selected) == 1
    assert selected[0].function_id == "func/f"


@pytest.mark.unit
def test_select_sites_lines_filter():
    sites = [_make_site(0, 1, "func/f"), _make_site(1, 2, "func/g")]
    covered = {1, 2}
    _, selected = _select_sites(sites, covered, set(), effective_since_last_run=False, lines_filter={1})
    assert len(selected) == 1
    assert selected[0].line == 1


@pytest.mark.unit
def test_select_sites_uncovered_excluded():
    sites = [_make_site(0, 1, "func/f"), _make_site(1, 2, "func/g")]
    covered = {1}  # line 2 uncovered
    _, selected = _select_sites(sites, covered, set(), effective_since_last_run=False, lines_filter=None)
    assert len(selected) == 1
    assert selected[0].line == 1


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


# ── _is_effective_since_last_run logic ───────────────────────────────────────


@pytest.mark.unit
def test_is_effective_since_last_run_explicit():
    """since_last_run=True -> effective regardless of other flags."""
    assert (
        _is_effective_since_last_run(since_last_run=True, manifest_exists=False, mutate_all=True, lines_filter={1, 2})
        is True
    )


@pytest.mark.unit
def test_is_effective_since_last_run_implicit_all_conditions():
    """manifest exists, mutate_all=False, no lines_filter -> effective."""
    assert (
        _is_effective_since_last_run(since_last_run=False, manifest_exists=True, mutate_all=False, lines_filter=None)
        is True
    )


@pytest.mark.unit
def test_is_effective_since_last_run_no_manifest():
    """No manifest -> not effective via implicit path."""
    assert (
        _is_effective_since_last_run(since_last_run=False, manifest_exists=False, mutate_all=False, lines_filter=None)
        is False
    )


@pytest.mark.unit
def test_is_effective_since_last_run_mutate_all_disables():
    """mutate_all=True -> not effective via implicit path."""
    assert (
        _is_effective_since_last_run(since_last_run=False, manifest_exists=True, mutate_all=True, lines_filter=None)
        is False
    )


@pytest.mark.unit
def test_is_effective_since_last_run_lines_filter_disables():
    """lines_filter present -> not effective via implicit path."""
    assert (
        _is_effective_since_last_run(since_last_run=False, manifest_exists=True, mutate_all=False, lines_filter={5})
        is False
    )
