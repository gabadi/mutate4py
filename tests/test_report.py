"""Unit tests for the report module (_report.py)."""

from mutate4py._discovery import Site
from mutate4py._report import (
    OverheadInfo,
    RunStats,
    _mutation_report_lines,
    _on_parallel_result,
    _overhead_report_lines,
    _parallel_progress_line,
    _run_header_lines,
    _serial_progress_line,
    _uncovered_block_lines,
    _workers_header_lines,
)


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


# ── _uncovered_block_lines ────────────────────────────────────────────────────


def test_uncovered_block_lines_with_uncovered():
    sites = [
        _make_site(0, 1, "func/f"),
        _make_site(1, 2, "func/g"),
    ]
    covered_lines = {1}  # line 2 is uncovered
    lines = _uncovered_block_lines(sites, covered_lines)
    assert lines[0] == "Uncovered mutations:"
    assert any("line 2" in ln and "func/g" in ln for ln in lines)


def test_uncovered_block_lines_no_uncovered():
    sites = [_make_site(0, 1, "func/f"), _make_site(1, 2, "func/g")]
    covered_lines = {1, 2}
    assert _uncovered_block_lines(sites, covered_lines) == []


def test_uncovered_block_lines_no_function_id():
    site = Site(
        index=0,
        line=5,
        col=0,
        end_line=5,
        end_col=3,
        function_id="",
        orig_text=">",
        mutant_text=">=",
        desc="> -> >=",
    )
    lines = _uncovered_block_lines([site], set())
    assert lines == ["Uncovered mutations:", "  line 5 > -> >="]


# ── _run_header_lines ─────────────────────────────────────────────────────────


def _make_run_stats(**overrides) -> RunStats:
    defaults = dict(
        total=5,
        covered_count=4,
        uncovered_count=1,
        changed_count=5,
        manifest_exists=False,
        selected_count=4,
        warning_threshold=1000,
    )
    defaults.update(overrides)
    return RunStats(**defaults)


def test_run_header_lines_field_order_and_content():
    lines = _run_header_lines("calc.py", _make_run_stats())
    assert lines == [
        "Mutation run: calc.py",
        "Total mutation sites: 5",
        "Covered mutation sites: 4",
        "Uncovered mutation sites: 1",
        "Changed mutation sites: 5",
        "Manifest exists: false",
        "Selected mutation sites: 4",
    ]


def test_run_header_lines_manifest_exists_true():
    lines = _run_header_lines("calc.py", _make_run_stats(manifest_exists=True))
    assert "Manifest exists: true" in lines


def test_run_header_lines_warning_above_threshold():
    lines = _run_header_lines("calc.py", _make_run_stats(total=2000, warning_threshold=1000))
    assert lines[-1] == "Warning: 2000 mutation sites exceeds threshold 1000."


def test_run_header_lines_no_warning_at_threshold():
    lines = _run_header_lines("calc.py", _make_run_stats(total=1000, warning_threshold=1000))
    assert not any(ln.startswith("Warning:") for ln in lines)


# ── _workers_header_lines ─────────────────────────────────────────────────────


def test_workers_header_lines_zero_workers_is_empty():
    assert _workers_header_lines(0, use_parallel=False, n_selected=3) == []


def test_workers_header_lines_serial():
    assert _workers_header_lines(1, use_parallel=False, n_selected=3) == ["Mutation workers: 1"]


def test_workers_header_lines_parallel_clamped_to_selected():
    assert _workers_header_lines(8, use_parallel=True, n_selected=3) == ["Mutation workers: 3"]


def test_workers_header_lines_parallel_not_clamped():
    assert _workers_header_lines(2, use_parallel=True, n_selected=5) == ["Mutation workers: 2"]


# ── _serial_progress_line ─────────────────────────────────────────────────────


def test_serial_progress_line_with_function_id():
    site = _make_site(0, 7, "func/f")
    line = _serial_progress_line(2, 5, "survived", site)
    assert line == "[2/5] survived line 7 > -> >=: func/f"


def test_serial_progress_line_without_function_id():
    site = _make_site(0, 7, "")
    line = _serial_progress_line(2, 5, "killed", site)
    assert line == "[2/5] killed line 7 > -> >="


# ── _mutation_report_lines ────────────────────────────────────────────────────


def test_mutation_report_lines_no_survivors():
    lines = _mutation_report_lines({"killed": 2, "timeout": 1, "survived": 0}, [], uncovered_count=1)
    assert lines == [
        "",
        "Mutation Report",
        "===============",
        "Killed: 3",
        "Survived: 0",
        "Uncovered: 1",
    ]


def test_mutation_report_lines_with_survivors():
    survivor = _make_site(0, 4, "func/f")
    lines = _mutation_report_lines({"killed": 0, "timeout": 0, "survived": 1}, [survivor], uncovered_count=0)
    assert lines[-3:] == ["", "Survivors:", "  line 4 > -> >= func/f"]


def test_mutation_report_lines_selection_counts_included():
    lines = _mutation_report_lines(
        {"killed": 1, "timeout": 0, "survived": 0},
        [],
        uncovered_count=0,
        selection_counts={"narrowed": 3, "static": 1},
    )
    assert "Test selection: narrowed 3, static 1" in lines


def test_mutation_report_lines_omits_selection_line_without_a_context_db():
    lines = _mutation_report_lines({"killed": 1, "timeout": 0, "survived": 0}, [], uncovered_count=0)
    assert not any(ln.startswith("Test selection:") for ln in lines)


# ── _overhead_report_lines (issue 06) ─────────────────────────────────────────
#
# Every assertion here is against synthetic overhead/baseline values chosen to
# land clearly above or below the threshold — never against a real measured
# duration, which is machine-dependent.


def test_overhead_report_lines_prints_the_measured_value():
    lines = _overhead_report_lines(0.42, 10.0)
    assert lines[0] == "Per-Mutant overhead: 0.42s"


def test_overhead_report_lines_no_hint_when_overhead_is_small():
    lines = _overhead_report_lines(0.1, 10.0)  # 1% of baseline
    assert len(lines) == 1
    assert not any(ln.startswith("Hint:") for ln in lines)


def test_overhead_report_lines_hint_when_overhead_is_large():
    lines = _overhead_report_lines(8.0, 10.0)  # 80% of baseline
    assert any(ln.startswith("Hint:") for ln in lines)


def test_overhead_report_lines_hint_names_pytest_args_flag():
    lines = _overhead_report_lines(8.0, 10.0)
    hint = next(ln for ln in lines if ln.startswith("Hint:"))
    assert "--pytest-args" in hint


def test_overhead_report_lines_hint_absent_exactly_below_threshold():
    lines = _overhead_report_lines(4.999, 10.0)  # 49.99% of baseline
    assert not any(ln.startswith("Hint:") for ln in lines)


def test_overhead_report_lines_hint_present_exactly_at_threshold():
    lines = _overhead_report_lines(5.0, 10.0)  # exactly 50% of baseline
    assert any(ln.startswith("Hint:") for ln in lines)


def test_overhead_report_lines_no_hint_when_baseline_is_zero():
    """Guards the division: a zero baseline must never raise or spuriously hint."""
    lines = _overhead_report_lines(1.0, 0.0)
    assert len(lines) == 1


# ── _mutation_report_lines: overhead wiring ───────────────────────────────────


def test_mutation_report_lines_includes_overhead_when_provided():
    lines = _mutation_report_lines(
        {"killed": 1, "timeout": 0, "survived": 0},
        [],
        uncovered_count=0,
        overhead=OverheadInfo(overhead_duration=0.33, baseline_duration=10.0),
    )
    assert "Per-Mutant overhead: 0.33s" in lines


def test_mutation_report_lines_omits_overhead_when_not_provided():
    lines = _mutation_report_lines({"killed": 1, "timeout": 0, "survived": 0}, [], uncovered_count=0)
    assert not any(ln.startswith("Per-Mutant overhead:") for ln in lines)


def test_mutation_report_lines_overhead_sits_after_uncovered_and_before_survivors():
    survivor = _make_site(0, 4, "func/f")
    lines = _mutation_report_lines(
        {"killed": 0, "timeout": 0, "survived": 1},
        [survivor],
        uncovered_count=0,
        overhead=OverheadInfo(overhead_duration=8.0, baseline_duration=10.0),
    )
    uncovered_idx = next(i for i, ln in enumerate(lines) if ln.startswith("Uncovered:"))
    overhead_idx = next(i for i, ln in enumerate(lines) if ln.startswith("Per-Mutant overhead:"))
    survivors_idx = lines.index("Survivors:")
    assert uncovered_idx < overhead_idx < survivors_idx


# ── _parallel_progress_line ───────────────────────────────────────────────────


def _make_simple_site(line=42, function_id=""):
    return Site(
        index=0,
        line=line,
        col=11,
        end_line=line,
        end_col=12,
        function_id=function_id,
        orig_text=">",
        mutant_text=">=",
        desc="> -> >=",
    )


def test_parallel_progress_line_includes_worker_idx():
    """worker_idx from result dict must appear in the formatted progress line."""
    result = {
        "site": _make_simple_site(42),
        "site_idx": 3,
        "total": 10,
        "worker_idx": 7,
        "status": "survived",
    }
    line = _parallel_progress_line(result)
    assert "worker-7" in line
    assert "[3/10]" in line


def test_parallel_progress_line_different_worker_idx():
    """A different worker_idx produces a different label — ensures idx is not hardcoded."""
    result = {
        "site": _make_simple_site(1),
        "site_idx": 1,
        "total": 5,
        "worker_idx": 2,
        "status": "killed",
    }
    line = _parallel_progress_line(result)
    assert "worker-2" in line
    assert "worker-7" not in line


def test_parallel_progress_line_fid_suffix_when_empty():
    """When function_id is empty, no trailing colon-suffix in the line."""
    result = {
        "site": _make_simple_site(10, function_id=""),
        "site_idx": 1,
        "total": 1,
        "worker_idx": 1,
        "status": "killed",
    }
    line = _parallel_progress_line(result)
    assert line.endswith("> -> >="), f"No extra suffix expected, got: {line!r}"


def test_parallel_progress_line_fid_suffix_when_present():
    """When function_id is non-empty, the line ends with ': <function_id>'."""
    result = {
        "site": _make_simple_site(10, function_id="func/calc"),
        "site_idx": 2,
        "total": 4,
        "worker_idx": 3,
        "status": "killed",
    }
    line = _parallel_progress_line(result)
    assert ": func/calc" in line, f"Expected fid suffix, got: {line!r}"


def test_on_parallel_result_prints_the_formatted_line(capsys):
    """The print callback delegates to _parallel_progress_line verbatim."""
    result = {
        "site": _make_simple_site(42),
        "site_idx": 3,
        "total": 10,
        "worker_idx": 7,
        "status": "survived",
    }
    _on_parallel_result(result)
    out = capsys.readouterr().out
    assert out == _parallel_progress_line(result) + "\n"
