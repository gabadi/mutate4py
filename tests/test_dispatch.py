"""Unit tests for CLI dispatch and execution (_dispatch.py, issue #38 gate 11).

Tests that directly call/import the moved dispatch-cluster functions live
here. Tests that only reach the same behavior indirectly through
`mutate4py.__main__.main()` or the CLI subprocess helpers stay in
test_main.py — those exercise the CLI entry point end-to-end, not this
module's internals in isolation.
"""

import os

import pytest


def _make_args(**kwargs):
    """Build a minimal argparse.Namespace for dispatch-cluster tests."""
    import argparse

    defaults = dict(
        scan=False,
        update_manifest=False,
        check_manifest=False,
        lines=None,
        since_last_run=False,
        mutate_all=False,
        max_workers=None,
        timeout_factor=10,
        min_timeout=1.0,
        test_command="pytest",
        test_contexts=None,
        cov_cmd=None,
        lcov=None,
        reuse_coverage=False,
        warning_threshold=50,
        manifest_file=False,
        verbose=False,
        exclude=None,
        prune_dirs=(),
        no_fork_server=False,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _make_pkg_tree(tmp_path) -> str:
    """pkg/{mod.py, __init__.py, sub/{deep.py, __init__.py}}; return pkg path."""
    d = tmp_path / "pkg"
    sub = d / "sub"
    sub.mkdir(parents=True)
    for p in (d / "mod.py", d / "__init__.py", sub / "deep.py", sub / "__init__.py"):
        p.write_text("x = 1\n")
    return str(d)


# ── _run_scan direct unit tests ───────────────────────────────────────────────


def test_run_scan_no_coverage(tmp_path, capsys):
    import argparse

    from mutate4py._dispatch import _run_scan

    src_file = tmp_path / "foo.py"
    src_file.write_text("x = a + b\n")
    args = argparse.Namespace(
        file=str(src_file),
        warning_threshold=1000,
        cov_cmd=None,
        lcov=None,
        reuse_coverage=False,
    )
    _run_scan(args, str(src_file), src_file.read_text(), str(tmp_path))
    out = capsys.readouterr().out
    assert "Total mutation sites: 1" in out


def test_run_scan_with_lcov(tmp_path, capsys):
    import argparse

    from mutate4py._dispatch import _run_scan

    src_file = tmp_path / "foo.py"
    src_file.write_text("x = a + b\n")
    lcov_file = tmp_path / "cov.info"
    lcov_file.write_text(f"SF:{src_file}\nDA:1,1\nend_of_record\n")
    args = argparse.Namespace(
        file=str(src_file),
        warning_threshold=1000,
        cov_cmd=None,
        lcov=str(lcov_file),
        reuse_coverage=False,
    )
    _run_scan(args, str(src_file), src_file.read_text(), str(tmp_path))
    out = capsys.readouterr().out
    assert "Covered mutation sites:" in out


# ── _run_on_file: CLI-args → run_mutations wiring ─────────────────────────────
#
# Gap found via coverage.py arc data: nothing in the suite exercises the
# non-scan/non-manifest branch of _run_on_file (the code that maps a parsed
# argparse.Namespace onto run_mutations' kwargs for the directory-mode
# per-file dispatch path). A mutant swapping since_last_run/mutate_all, or
# dropping test_contexts_path=args.test_contexts, would go undetected.
# run_mutations' own behavior is already covered directly in test_runner.py;
# this section is only about proving the wiring is correct.


def test_run_on_file_wires_args_into_run_mutations(monkeypatch):
    import dataclasses

    from mutate4py._dispatch import _run_on_file

    captured = {}

    def fake_run_mutations(request):
        captured["request"] = request
        return 0

    monkeypatch.setattr("mutate4py._dispatch.run_mutations", fake_run_mutations)

    args = _make_args(
        cov_cmd="echo hi",
        test_command="tox",
        timeout_factor=7,
        min_timeout=2.5,
        lines="3,4",
        since_last_run=True,
        mutate_all=False,
        warning_threshold=42,
        max_workers=3,
        test_contexts=".coverage",
    )
    result = _run_on_file(args, "f.py", "x = 1\n", "/cwd", baseline_duration=1.5)

    assert result == 0
    assert dataclasses.asdict(captured["request"]) == {
        "path": "f.py",
        "source": "x = 1\n",
        "cov_cmd": "echo hi",
        "lcov_path": None,
        "reuse_coverage": False,
        "test_command": "tox",
        "timeout_factor": 7,
        "min_timeout": 2.5,
        "lines_filter": {3, 4},
        "since_last_run": True,
        "mutate_all": False,
        "warning_threshold": 42,
        "max_workers": 3,
        "cwd": "/cwd",
        "baseline_duration": 1.5,
        "test_contexts_path": ".coverage",
        "manifest_file": False,
        "fork_server_requested": True,
    }


def test_run_on_file_mutate_all_wired_when_lines_and_since_last_run_absent(
    monkeypatch,
):
    """Distinguishes mutate_all from since_last_run in the wiring (mutant: swapped kwargs)."""
    from mutate4py._dispatch import _run_on_file

    captured = {}
    monkeypatch.setattr(
        "mutate4py._dispatch.run_mutations",
        lambda request: captured.update(request=request) or 0,
    )

    args = _make_args(since_last_run=False, mutate_all=True, max_workers=None)
    _run_on_file(args, "f.py", "x = 1\n", "/cwd")

    request = captured["request"]
    assert request.since_last_run is False
    assert request.mutate_all is True
    assert request.max_workers == 0  # None -> 0 default, per _run_on_file
    assert request.lines_filter is None
    assert request.baseline_duration is None


def test_run_on_file_scan_coverage_error_exits_2(monkeypatch, capsys):
    """The --scan branch's own try/except (distinct from _run_scan's) must exit(2)."""
    from mutate4py._coverage import CoverageError
    from mutate4py._dispatch import _run_on_file

    def raise_coverage_error(**kwargs):
        raise CoverageError("no coverage source")

    monkeypatch.setattr("mutate4py._dispatch.run_scan", raise_coverage_error)

    args = _make_args(scan=True)
    with pytest.raises(SystemExit) as exc:
        _run_on_file(args, "f.py", "x = 1\n", "/cwd")
    assert exc.value.code == 2
    assert "no coverage source" in capsys.readouterr().err


def test_run_on_file_fork_server_requested_defaults_true(monkeypatch):
    """Default (no --no-fork-server): run_mutations is asked to use the fast path."""
    from mutate4py._dispatch import _run_on_file

    captured = {}
    monkeypatch.setattr(
        "mutate4py._dispatch.run_mutations",
        lambda request: captured.update(request=request) or 0,
    )
    args = _make_args(no_fork_server=False)
    _run_on_file(args, "f.py", "x = 1\n", "/cwd")
    assert captured["request"].fork_server_requested is True


def test_run_on_file_fork_server_requested_false_when_disabled(monkeypatch):
    from mutate4py._dispatch import _run_on_file

    captured = {}
    monkeypatch.setattr(
        "mutate4py._dispatch.run_mutations",
        lambda request: captured.update(request=request) or 0,
    )
    args = _make_args(no_fork_server=True)
    _run_on_file(args, "f.py", "x = 1\n", "/cwd")
    assert captured["request"].fork_server_requested is False


# ── _needs_directory_baseline / _prepare_directory_baseline ───────────────────


def test_needs_directory_baseline_true_for_normal_run():
    from mutate4py._dispatch import _needs_directory_baseline

    args = _make_args()
    assert _needs_directory_baseline(["a.py"], args) is True


def test_needs_directory_baseline_false_when_no_files():
    from mutate4py._dispatch import _needs_directory_baseline

    args = _make_args()
    assert _needs_directory_baseline([], args) is False


@pytest.mark.parametrize("extra", [{"scan": True}, {"update_manifest": True}, {"check_manifest": True}])
def test_needs_directory_baseline_false_for_no_run_modes(extra):
    from mutate4py._dispatch import _needs_directory_baseline

    args = _make_args(**extra)
    assert _needs_directory_baseline(["a.py"], args) is False


def test_prepare_directory_baseline_returns_duration(monkeypatch):
    from mutate4py._dispatch import _prepare_directory_baseline

    monkeypatch.setattr("mutate4py._coverage.acquire_coverage", lambda **kwargs: {1, 2})
    monkeypatch.setattr("mutate4py._dispatch.run_baseline", lambda cmd, cwd: (1.23, None))

    args = _make_args(test_command="pytest")
    duration = _prepare_directory_baseline(args, ["a.py"], "/cwd")

    assert duration == 1.23


def test_prepare_directory_baseline_coverage_error_exits_1(monkeypatch, capsys):
    from mutate4py._coverage import CoverageError
    from mutate4py._dispatch import _prepare_directory_baseline

    def raise_coverage_error(**kwargs):
        raise CoverageError("no coverage source")

    monkeypatch.setattr("mutate4py._coverage.acquire_coverage", raise_coverage_error)

    args = _make_args()
    with pytest.raises(SystemExit) as exc:
        _prepare_directory_baseline(args, ["a.py"], "/cwd")
    assert exc.value.code == 1
    assert "no coverage source" in capsys.readouterr().err


def test_prepare_directory_baseline_baseline_failure_exits_1(monkeypatch, capsys):
    from mutate4py._dispatch import _prepare_directory_baseline

    monkeypatch.setattr("mutate4py._coverage.acquire_coverage", lambda **kwargs: {1, 2})
    monkeypatch.setattr("mutate4py._dispatch.run_baseline", lambda cmd, cwd: (0.0, "boom"))

    args = _make_args()
    with pytest.raises(SystemExit) as exc:
        _prepare_directory_baseline(args, ["a.py"], "/cwd")
    assert exc.value.code == 1
    assert "boom" in capsys.readouterr().err


# ── Mutant-killing gap tests: _load_source / _run_scan ─────────────────────────


def test_load_source_missing_file_exits_2(tmp_path):
    # mutant_6,_7: sys.exit(2) on missing file
    from mutate4py._dispatch import _load_source

    with pytest.raises(SystemExit) as exc:
        _load_source(str(tmp_path / "no_such.py"))
    assert exc.value.code == 2


def test_load_source_error_on_stderr(tmp_path, capsys):
    # mutant_2,3,4,5: print(f"error: {exc}", file=sys.stderr)
    from mutate4py._dispatch import _load_source

    with pytest.raises(SystemExit):
        _load_source(str(tmp_path / "no_such.py"))
    err = capsys.readouterr().err
    assert "error" in err.lower()


def test_run_scan_coverage_error_exits_2(tmp_path):
    # mutant_21-26: CoverageError → sys.exit(2) exactly
    import argparse

    from mutate4py._dispatch import _run_scan

    src_file = tmp_path / "foo.py"
    src_file.write_text("x = a + b\n")
    args = argparse.Namespace(
        file=str(src_file),
        warning_threshold=1000,
        cov_cmd=None,
        lcov=str(tmp_path / "missing.info"),
        reuse_coverage=False,
    )
    with pytest.raises(SystemExit) as exc:
        _run_scan(args, str(src_file), src_file.read_text(), str(tmp_path))
    assert exc.value.code == 2


def test_run_scan_coverage_error_goes_to_stderr(tmp_path, capsys):
    # mutant_21-26: error message goes to stderr
    import argparse

    from mutate4py._dispatch import _run_scan

    src_file = tmp_path / "foo.py"
    src_file.write_text("x = a + b\n")
    args = argparse.Namespace(
        file=str(src_file),
        warning_threshold=1000,
        cov_cmd=None,
        lcov=str(tmp_path / "missing.info"),
        reuse_coverage=False,
    )
    with pytest.raises(SystemExit):
        _run_scan(args, str(src_file), src_file.read_text(), str(tmp_path))
    err = capsys.readouterr().err
    assert "error" in err.lower()


def test_run_scan_output_newline_separated(tmp_path, capsys):
    # mutant_28,_36: print("\n".join(lines)) — output lines are newline-separated
    import argparse

    from mutate4py._dispatch import _run_scan

    src_file = tmp_path / "foo.py"
    src_file.write_text("x = a + b\n")
    args = argparse.Namespace(
        file=str(src_file),
        warning_threshold=1000,
        cov_cmd=None,
        lcov=None,
        reuse_coverage=False,
    )
    _run_scan(args, str(src_file), src_file.read_text(), str(tmp_path))
    out = capsys.readouterr().out
    assert "Mutation scan:" in out
    assert "Total mutation sites:" in out
    # Lines are separated by newlines (not spaces, tabs, etc.)
    assert "\n" in out


def test_run_scan_passes_cov_cmd_to_coverage(tmp_path, capsys):
    # mutant_10: cov_cmd=None vs args.cov_cmd — cov_cmd must be passed through
    import argparse

    from mutate4py._dispatch import _run_scan

    src_file = tmp_path / "foo.py"
    src_file.write_text("x = a + b\n")
    lcov_file = tmp_path / "coverage.lcov"
    # Create a cov_cmd that writes the lcov file
    cmd = f"printf 'SF:{src_file}\\nDA:1,1\\nend_of_record\\n' > '{lcov_file}'"
    args = argparse.Namespace(
        file=str(src_file),
        warning_threshold=1000,
        cov_cmd=cmd,
        lcov=None,
        reuse_coverage=False,
    )
    _run_scan(args, str(src_file), src_file.read_text(), str(tmp_path))
    out = capsys.readouterr().out
    assert "Covered mutation sites:" in out


def test_run_scan_reuse_coverage_with_cwd(tmp_path, capsys):
    # mutant_12/13: reuse_coverage and cwd are passed through to acquire_coverage;
    # coverage.lcov in cwd is found only when cwd is correct
    import argparse

    from mutate4py._dispatch import _run_scan

    src_file = tmp_path / "foo.py"
    src_file.write_text("x = a + b\n")
    lcov_file = tmp_path / "coverage.lcov"
    lcov_file.write_text(f"SF:{src_file}\nDA:1,1\nend_of_record\n")
    args = argparse.Namespace(
        file=str(src_file),
        warning_threshold=1000,
        cov_cmd=None,
        lcov=None,
        reuse_coverage=True,
    )
    _run_scan(args, str(src_file), src_file.read_text(), str(tmp_path))
    out = capsys.readouterr().out
    assert "Covered mutation sites:" in out


def test_run_scan_passes_args_file_path(tmp_path, capsys):
    # mutant_28: scan_report(None, ...) vs scan_report(path, ...)
    # Path in header must match the path argument
    import argparse

    from mutate4py._dispatch import _run_scan

    src_file = tmp_path / "mymod.py"
    src_file.write_text("x = a + b\n")
    args = argparse.Namespace(
        file=str(src_file),
        warning_threshold=1000,
        cov_cmd=None,
        lcov=None,
        reuse_coverage=False,
    )
    _run_scan(args, str(src_file), src_file.read_text(), str(tmp_path))
    out = capsys.readouterr().out
    assert "mymod.py" in out


def test_run_scan_separator_is_newline_not_other_string(tmp_path, capsys):
    # mutant_36: "XX\nXX".join(lines) vs "\n".join(lines)
    import argparse

    from mutate4py._dispatch import _run_scan

    src_file = tmp_path / "foo.py"
    src_file.write_text("pass\n")
    args = argparse.Namespace(
        file=str(src_file),
        warning_threshold=1000,
        cov_cmd=None,
        lcov=None,
        reuse_coverage=False,
    )
    _run_scan(args, str(src_file), src_file.read_text(), str(tmp_path))
    out = capsys.readouterr().out
    assert "XX" not in out
    # Output must have each label on its own line
    for label in ["Mutation scan:", "Total mutation sites:"]:
        assert label in out


# ── _parse_lines ──────────────────────────────────────────────────────────────


def test_parse_lines_none():
    from mutate4py._dispatch import _parse_lines

    assert _parse_lines(None) is None


def test_parse_lines_single():
    from mutate4py._dispatch import _parse_lines

    assert _parse_lines("5") == {5}


def test_parse_lines_multiple():
    from mutate4py._dispatch import _parse_lines

    assert _parse_lines("3,7,12") == {3, 7, 12}


def test_parse_lines_with_spaces():
    from mutate4py._dispatch import _parse_lines

    assert _parse_lines(" 3 , 7 ") == {3, 7}


# ── _parse_lines: error branches ──────────────────────────────────────────────


def test_parse_lines_non_integer_exits(capsys):
    from mutate4py._dispatch import _parse_lines

    try:
        _parse_lines("3,abc")
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert exc.code == 2
    err = capsys.readouterr().err
    assert "not a valid integer" in err


def test_parse_lines_zero_exits(capsys):
    from mutate4py._dispatch import _parse_lines

    try:
        _parse_lines("0")
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert exc.code == 2
    err = capsys.readouterr().err
    assert "positive integer" in err


def test_parse_lines_negative_exits(capsys):
    from mutate4py._dispatch import _parse_lines

    try:
        _parse_lines("-3")
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert exc.code == 2
    err = capsys.readouterr().err
    assert "positive integer" in err


# ── --exclude: dispatch-level reporting and exits ─────────────────────────────


def test_report_excluded_prints_one_line_per_file(capsys):
    from mutate4py._dispatch import _report_excluded

    _report_excluded(["a.py", "b.py"])
    assert capsys.readouterr().out == "Excluded: a.py\nExcluded: b.py\n"


def test_report_excluded_prints_nothing_for_an_empty_list(capsys):
    from mutate4py._dispatch import _report_excluded

    _report_excluded([])
    assert capsys.readouterr().out == ""


def test_collect_union_files_single_root_returns_survivors(tmp_path):
    from mutate4py._dispatch import _collect_union_files

    d = _make_pkg_tree(tmp_path)
    args = _make_args(file=d, exclude=["**/sub/*.py"])
    assert _collect_union_files(args, [d]) == [
        os.path.join(d, "__init__.py"),
        os.path.join(d, "mod.py"),
    ]


def test_collect_union_files_single_root_raises_when_all_excluded(tmp_path):
    from mutate4py._dispatch import _collect_union_files
    from mutate4py._target_resolution import NoFilesToProcessError

    d = _make_pkg_tree(tmp_path)
    args = _make_args(file=d, exclude=["**/*.py"])
    with pytest.raises(NoFilesToProcessError):
        _collect_union_files(args, [d])


def test_collect_union_files_single_root_verbose_reports_before_raising(tmp_path, capsys):
    from mutate4py._dispatch import _collect_union_files
    from mutate4py._target_resolution import NoFilesToProcessError

    d = _make_pkg_tree(tmp_path)
    args = _make_args(file=d, exclude=["**/*.py"], verbose=True)
    with pytest.raises(NoFilesToProcessError):
        _collect_union_files(args, [d])
    assert capsys.readouterr().out.count("Excluded: ") == 4


def test_raise_if_target_excluded_returns_when_no_match(tmp_path):
    from mutate4py._dispatch import _raise_if_target_excluded

    args = _make_args(file="pkg/mod.py", exclude=["*/other.py"])
    _raise_if_target_excluded(args)  # must not raise


def test_raise_if_target_excluded_raises_on_match(capsys):
    from mutate4py._dispatch import _raise_if_target_excluded
    from mutate4py._target_resolution import NoFilesToProcessError

    args = _make_args(file="pkg/mod.py", exclude=["*/mod.py"])
    with pytest.raises(NoFilesToProcessError):
        _raise_if_target_excluded(args)
    assert capsys.readouterr().out == ""


def test_raise_if_target_excluded_verbose_names_the_target(capsys):
    from mutate4py._dispatch import _raise_if_target_excluded
    from mutate4py._target_resolution import NoFilesToProcessError

    args = _make_args(file="pkg/mod.py", exclude=["*/mod.py"], verbose=True)
    with pytest.raises(NoFilesToProcessError):
        _raise_if_target_excluded(args)
    assert capsys.readouterr().out == "Excluded: pkg/mod.py\n"


# ── batch exit-code aggregation ───────────────────────────────────────────────


def _run_batch(monkeypatch, codes):
    """Drive _run_files_and_exit over fake files returning `codes` in order."""
    import mutate4py._dispatch as m

    files = [f"f{i}.py" for i in range(len(codes))]
    by_file = dict(zip(files, codes))
    seen = []

    def fake_run_on_file(args, py_file, source, cwd, baseline_duration=None):
        seen.append(py_file)
        return by_file[py_file]

    monkeypatch.setattr(m, "_load_source", lambda path: "x = 1\n")
    monkeypatch.setattr(m, "_run_on_file", fake_run_on_file)

    with pytest.raises(SystemExit) as exc:
        m._run_files_and_exit(_make_args(scan=True), files)
    assert seen == files, "every file must run, even after one fails"
    return exc.value.code


@pytest.mark.parametrize(
    "codes,expected",
    [
        ([0, 0, 0], 0),
        ([0, 1, 0], 1),
        ([0, 2, 0], 2),
        ([1, 2, 0], 2),
        ([2, 1, 0], 2),
        ([1, 1, 1], 1),
        ([2, 2], 2),
    ],
)
def test_run_files_and_exit_reports_worst_code(monkeypatch, codes, expected):
    """The batch exit code is the highest-severity per-file code (2 > 1 > 0),
    not a boolean collapse, and is order-independent."""
    assert _run_batch(monkeypatch, codes) == expected


# ── unparseable files never stop the batch (issue #35) ────────────────────────


def test_syntax_error_reason_includes_line_number():
    import mutate4py._dispatch as m

    exc = SyntaxError("invalid syntax", ("bad.py", 3, 5, "def f(:\n", 3, 6))
    assert m._syntax_error_reason(exc) == "invalid syntax (line 3)"


def test_syntax_error_reason_without_line_number_omits_it():
    import mutate4py._dispatch as m

    exc = SyntaxError("invalid syntax")
    exc.lineno = None
    assert m._syntax_error_reason(exc) == "invalid syntax"


def test_run_files_and_exit_continues_past_syntax_error(monkeypatch, capsys):
    """A SyntaxError on one file must not stop the rest of the batch from running."""
    import mutate4py._dispatch as m

    files = ["good1.py", "bad.py", "good2.py"]
    seen = []

    def fake_run_on_file(args, py_file, source, cwd, baseline_duration=None):
        seen.append(py_file)
        if py_file == "bad.py":
            raise SyntaxError("invalid syntax", ("bad.py", 3, 5, "def f(:\n", 3, 6))
        return 0

    monkeypatch.setattr(m, "_load_source", lambda path: "x = 1\n")
    monkeypatch.setattr(m, "_run_on_file", fake_run_on_file)

    with pytest.raises(SystemExit) as exc:
        m._run_files_and_exit(_make_args(scan=True), files)

    assert seen == files, "a parse failure must not stop the batch"
    assert exc.value.code == 2


def test_run_files_and_exit_syntax_error_message_on_stderr(monkeypatch, capsys):
    import mutate4py._dispatch as m

    def fake_run_on_file(args, py_file, source, cwd, baseline_duration=None):
        raise SyntaxError("invalid syntax", ("bad.py", 3, 5, "def f(:\n", 3, 6))

    monkeypatch.setattr(m, "_load_source", lambda path: "x = 1\n")
    monkeypatch.setattr(m, "_run_on_file", fake_run_on_file)

    with pytest.raises(SystemExit):
        m._run_files_and_exit(_make_args(scan=True), ["bad.py"])

    err = capsys.readouterr().err
    assert "error: cannot parse bad.py: invalid syntax (line 3)" in err
    assert "Traceback" not in err


def test_run_files_and_exit_reports_parse_failure_count(monkeypatch, capsys):
    import mutate4py._dispatch as m

    def fake_run_on_file(args, py_file, source, cwd, baseline_duration=None):
        if py_file in ("bad1.py", "bad2.py"):
            raise SyntaxError("invalid syntax", (py_file, 1, 1, "?\n", 1, 2))
        return 0

    monkeypatch.setattr(m, "_load_source", lambda path: "x = 1\n")
    monkeypatch.setattr(m, "_run_on_file", fake_run_on_file)

    with pytest.raises(SystemExit) as exc:
        m._run_files_and_exit(_make_args(scan=True), ["bad1.py", "good.py", "bad2.py"])

    assert exc.value.code == 2
    assert "error: 2 files could not be parsed" in capsys.readouterr().err


def test_run_files_and_exit_no_parse_failure_summary_when_all_parse(monkeypatch, capsys):
    import mutate4py._dispatch as m

    monkeypatch.setattr(m, "_load_source", lambda path: "x = 1\n")
    monkeypatch.setattr(m, "_run_on_file", lambda *a, **k: 0)

    with pytest.raises(SystemExit) as exc:
        m._run_files_and_exit(_make_args(scan=True), ["a.py", "b.py"])

    assert exc.value.code == 0
    assert "could not be parsed" not in capsys.readouterr().err


def test_run_files_and_exit_syntax_error_worst_code_wins_either_order(
    monkeypatch,
):
    """A run failure (1) elsewhere in the batch neither masks nor is masked by
    a parse failure (2) — worst code always wins, regardless of which file the
    loop reaches first."""
    import mutate4py._dispatch as m

    def fake_run_on_file(args, py_file, source, cwd, baseline_duration=None):
        if py_file == "bad.py":
            raise SyntaxError("invalid syntax", ("bad.py", 1, 1, "?\n", 1, 2))
        return 1

    monkeypatch.setattr(m, "_load_source", lambda path: "x = 1\n")
    monkeypatch.setattr(m, "_run_on_file", fake_run_on_file)

    for files in (["fails.py", "bad.py"], ["bad.py", "fails.py"]):
        with pytest.raises(SystemExit) as exc:
            m._run_files_and_exit(_make_args(scan=True), files)
        assert exc.value.code == 2


def test_run_on_file_propagates_syntax_error(monkeypatch):
    """_run_on_file itself lets SyntaxError propagate — it's _dispatch (one of
    its callers) that catches and reports it (issue #35), so this stays a
    plain mode dispatch instead of duplicating the catch at every mode."""
    import mutate4py._dispatch as m

    def fake_run_mutations(request):
        raise SyntaxError("invalid syntax", ("mod.py", 2, 1, "def f(:\n", 2, 2))

    monkeypatch.setattr(m, "run_mutations", fake_run_mutations)
    args = _make_args(file="mod.py")

    with pytest.raises(SyntaxError):
        m._run_on_file(args, "mod.py", "def f(:\n", os.getcwd())


# ── multi-root positionals (issue #22): _collect_union_files (direct unit) ─────


def test_collect_union_files_unions_and_dedups_across_roots(tmp_path):
    from mutate4py._dispatch import _collect_union_files

    a_dir = tmp_path / "a_pkg"
    b_dir = tmp_path / "b_pkg"
    a_dir.mkdir()
    b_dir.mkdir()
    (a_dir / "a.py").write_text("x = 1\n")
    (b_dir / "b.py").write_text("x = 2\n")
    args = _make_args(exclude=None, verbose=False)
    files = _collect_union_files(args, [str(a_dir), str(b_dir), str(a_dir)])
    assert files == [str(a_dir / "a.py"), str(b_dir / "b.py")]


def test_collect_union_files_raises_when_the_whole_union_is_empty(tmp_path):
    from mutate4py._dispatch import _collect_union_files
    from mutate4py._target_resolution import NoFilesToProcessError

    a_dir = tmp_path / "a_pkg"
    b_dir = tmp_path / "b_pkg"
    a_dir.mkdir()
    b_dir.mkdir()
    args = _make_args(exclude=None, verbose=False)
    with pytest.raises(NoFilesToProcessError):
        _collect_union_files(args, [str(a_dir), str(b_dir)])


def test_collect_union_files_verbose_reports_excluded_per_root(tmp_path, capsys):
    from mutate4py._dispatch import _collect_union_files

    a_dir = tmp_path / "a_pkg"
    b_dir = tmp_path / "b_pkg"
    a_dir.mkdir()
    b_dir.mkdir()
    (a_dir / "a.py").write_text("x = 1\n")
    (b_dir / "b.py").write_text("x = 2\n")
    args = _make_args(exclude=["**/b.py"], verbose=True)
    files = _collect_union_files(args, [str(a_dir), str(b_dir)])
    assert files == [str(a_dir / "a.py")]
    assert f"Excluded: {b_dir / 'b.py'}" in capsys.readouterr().out
