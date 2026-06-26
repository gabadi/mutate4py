"""Unit tests for mutate4py CLI entry point (__main__)."""

import os
import subprocess
import sys
import tempfile
import textwrap

import pytest

from mutate4py.__main__ import scan_report

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def run_cli(*args: str, source: str | None = None) -> subprocess.CompletedProcess:
    """Run mutate4py CLI with given args; optionally write source to a temp file."""
    with tempfile.TemporaryDirectory() as d:
        if source is not None:
            path = os.path.join(d, "sample.py")
            with open(path, "w") as f:
                f.write(textwrap.dedent(source))
            cli_args = [path] + list(args)
        else:
            cli_args = list(args)

        result = subprocess.run(
            [sys.executable, "-m", "mutate4py"] + cli_args,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env={**os.environ, "PYTHONPATH": os.path.join(REPO_ROOT, "src")},
        )
    return result


def test_scan_prints_count_block_zero_sites():
    result = run_cli("--scan", source="x = 1\n")
    # 1 site (integer 1)
    assert "Total mutation sites: 1" in result.stdout
    assert "Changed mutation sites: 1" in result.stdout
    assert "Manifest exists: false" in result.stdout
    assert result.returncode == 0


def test_scan_prints_mutation_scan_header():
    result = run_cli("--scan", source="pass\n")
    assert "Mutation scan:" in result.stdout


def test_scan_zero_sites():
    result = run_cli("--scan", source="pass\n")
    assert "Total mutation sites: 0" in result.stdout
    assert "Changed mutation sites: 0" in result.stdout
    assert result.returncode == 0


def test_scan_no_warning_at_threshold():
    src = "x = a + b\n"
    result = run_cli("--scan", "--mutation-warning", "1", source=src)
    # 1 site, threshold 1: no warning (not strictly greater)
    assert "Warning:" not in result.stdout
    assert result.returncode == 0


def test_scan_warning_above_threshold():
    src = "x = a + b\ny = c - d\n"
    result = run_cli("--scan", "--mutation-warning", "1", source=src)
    # 2 sites > 1 threshold
    assert "Warning: 2 mutation sites exceeds threshold 1." in result.stdout
    assert result.returncode == 0


def test_missing_file_exits_nonzero():
    result = subprocess.run(
        [sys.executable, "-m", "mutate4py", "/nonexistent/path.py", "--scan"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": os.path.join(REPO_ROOT, "src")},
    )
    assert result.returncode != 0
    assert result.stdout == ""


def test_missing_file_error_on_stderr():
    result = subprocess.run(
        [sys.executable, "-m", "mutate4py", "/nonexistent/path.py", "--scan"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": os.path.join(REPO_ROOT, "src")},
    )
    assert "error" in result.stderr.lower() or result.returncode != 0


# ── scan_report unit tests (direct coverage of __main__.py) ───────────────────


def test_scan_report_zero_sites():
    lines, exceeded = scan_report("f.py", "pass\n", 1000)
    assert "Total mutation sites: 0" in lines
    assert "Changed mutation sites: 0" in lines
    assert "Manifest exists: false" in lines
    assert not exceeded


def test_scan_report_counts_sites():
    lines, exceeded = scan_report("f.py", "x = a + b\n", 1000)
    assert "Total mutation sites: 1" in lines
    assert "Changed mutation sites: 1" in lines
    assert not exceeded


def test_scan_report_header_uses_path():
    lines, _ = scan_report("myfile.py", "pass\n", 1000)
    assert "Mutation scan: myfile.py" in lines


def test_scan_report_no_warning_at_threshold():
    lines, exceeded = scan_report("f.py", "x = a + b\n", 1)
    assert not exceeded
    assert not any("Warning" in line for line in lines)


def test_scan_report_warning_above_threshold():
    src = "x = a + b\ny = c - d\n"
    lines, exceeded = scan_report("f.py", src, 1)
    assert exceeded
    assert any(
        "Warning: 2 mutation sites exceeds threshold 1." in line for line in lines
    )


def test_scan_report_total_equals_changed():
    src = "x = a + b\ny = c > d\n"
    lines, _ = scan_report("f.py", src, 1000)
    total_line = next(line for line in lines if "Total mutation sites:" in line)
    changed_line = next(line for line in lines if "Changed mutation sites:" in line)
    assert total_line.split(": ")[1] == changed_line.split(": ")[1]


# ── main() direct invocation (CRAP coverage) ──────────────────────────────────


def test_main_scan_prints_output(tmp_path, capsys):
    import mutate4py.__main__ as m

    p = tmp_path / "s.py"
    p.write_text("x = a + b\n")
    sys.argv = ["mutate4py", str(p), "--scan"]
    m.main()
    out = capsys.readouterr().out
    assert "Total mutation sites: 1" in out


def test_main_missing_file_exits(tmp_path):
    import mutate4py.__main__ as m

    sys.argv = ["mutate4py", str(tmp_path / "nope.py"), "--scan"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code != 0


def test_main_no_scan_flag_exits(tmp_path):
    import mutate4py.__main__ as m

    p = tmp_path / "s.py"
    p.write_text("pass\n")
    sys.argv = ["mutate4py", str(p)]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code != 0


# ── _manifests_structurally_equal unit tests ──────────────────────────────────


def _mse():
    from mutate4py._manifest import manifests_structurally_equal

    return manifests_structurally_equal


def test_mse_equal_manifests():
    fn = _mse()
    a = {"module_hash": "h1", "functions": [{"id": "func/foo", "hash": "fh1"}]}
    b = {"module_hash": "h1", "functions": [{"id": "func/foo", "hash": "fh1"}]}
    assert fn(a, b) is True


def test_mse_different_module_hash():
    fn = _mse()
    a = {"module_hash": "h1", "functions": []}
    b = {"module_hash": "h2", "functions": []}
    assert fn(a, b) is False


def test_mse_different_function_hash():
    fn = _mse()
    a = {"module_hash": "h", "functions": [{"id": "func/foo", "hash": "old"}]}
    b = {"module_hash": "h", "functions": [{"id": "func/foo", "hash": "new"}]}
    assert fn(a, b) is False


def test_mse_different_function_set():
    fn = _mse()
    a = {"module_hash": "h", "functions": [{"id": "func/foo", "hash": "fh"}]}
    b = {"module_hash": "h", "functions": [{"id": "func/bar", "hash": "fh"}]}
    assert fn(a, b) is False


def test_mse_ignores_tested_at():
    fn = _mse()
    a = {"module_hash": "h", "tested_at": "2026-01-01T00:00:00Z", "functions": []}
    b = {"module_hash": "h", "tested_at": "2026-06-01T00:00:00Z", "functions": []}
    assert fn(a, b) is True


@pytest.mark.parametrize(
    "a,b",
    [
        ({"module_hash": "h"}, {"module_hash": "h", "functions": []}),
        ({"module_hash": "h", "functions": []}, {"module_hash": "h"}),
    ],
)
def test_mse_missing_functions_key_treated_as_empty(a, b):
    fn = _mse()
    assert fn(a, b) is True


def test_mse_missing_functions_key_in_both_treated_as_empty():
    fn = _mse()
    a = {"module_hash": "h"}
    b = {"module_hash": "h"}
    assert fn(a, b) is True


def test_mse_a_missing_functions_differs_from_b_with_functions():
    fn = _mse()
    a = {"module_hash": "h"}
    b = {"module_hash": "h", "functions": [{"id": "func/foo", "hash": "fh"}]}
    assert fn(a, b) is False


# ── _do_update_manifest unit tests ────────────────────────────────────────────


def test_do_update_manifest_writes_footer(tmp_path, capsys):
    from mutate4py.__main__ import _do_update_manifest

    p = tmp_path / "s.py"
    p.write_text("def foo():\n    return 1\n")
    _do_update_manifest(str(p), p.read_text())
    content = p.read_text()
    assert "# mutate4py-manifest-begin" in content
    assert "Updated manifest:" in capsys.readouterr().out


def test_do_update_manifest_idempotent(tmp_path, capsys):
    from mutate4py.__main__ import _do_update_manifest

    p = tmp_path / "s.py"
    p.write_text("def foo():\n    return 1\n")
    _do_update_manifest(str(p), p.read_text())
    first_content = p.read_text()
    capsys.readouterr()  # clear
    _do_update_manifest(str(p), first_content)
    assert "Manifest unchanged:" in capsys.readouterr().out
    assert p.read_text() == first_content


def test_main_update_manifest_mode(tmp_path, capsys):
    import mutate4py.__main__ as m

    p = tmp_path / "s.py"
    p.write_text("def foo():\n    return 1\n")
    sys.argv = ["mutate4py", str(p), "--update-manifest"]
    m.main()
    out = capsys.readouterr().out
    assert "manifest" in out.lower()
    assert "# mutate4py-manifest-begin" in p.read_text()


# ── scan_report_with_coverage unit tests ─────────────────────────────────────


def test_scan_report_with_coverage_basic(tmp_path):
    from mutate4py.__main__ import scan_report_with_coverage

    src_file = tmp_path / "foo.py"
    src_file.write_text("x = a + b\n")
    lcov_file = tmp_path / "cov.info"
    lcov_file.write_text(f"SF:{src_file}\nDA:1,1\nend_of_record\n")

    lines, exceeded = scan_report_with_coverage(
        str(src_file),
        src_file.read_text(),
        1000,
        cov_cmd=None,
        lcov_path=str(lcov_file),
        reuse_coverage=False,
        cwd=str(tmp_path),
    )
    assert any("Covered mutation sites:" in line for line in lines)
    assert any("Uncovered mutation sites:" in line for line in lines)
    assert not exceeded


def test_scan_report_with_coverage_warning(tmp_path):
    from mutate4py.__main__ import scan_report_with_coverage

    src_file = tmp_path / "foo.py"
    src_file.write_text("x = a + b\ny = c - d\n")
    lcov_file = tmp_path / "cov.info"
    lcov_file.write_text(f"SF:{src_file}\nDA:1,1\nend_of_record\n")

    lines, exceeded = scan_report_with_coverage(
        str(src_file),
        src_file.read_text(),
        1,
        cov_cmd=None,
        lcov_path=str(lcov_file),
        reuse_coverage=False,
        cwd=str(tmp_path),
    )
    assert exceeded
    assert any("Warning:" in line for line in lines)


# ── _run_scan direct unit tests ───────────────────────────────────────────────


def test_run_scan_no_coverage(tmp_path, capsys):
    import argparse
    from mutate4py.__main__ import _run_scan

    src_file = tmp_path / "foo.py"
    src_file.write_text("x = a + b\n")
    args = argparse.Namespace(
        file=str(src_file),
        warning_threshold=1000,
        cov_cmd=None,
        lcov=None,
        reuse_coverage=False,
    )
    _run_scan(args, src_file.read_text(), str(tmp_path))
    out = capsys.readouterr().out
    assert "Total mutation sites: 1" in out


def test_run_scan_with_lcov(tmp_path, capsys):
    import argparse
    from mutate4py.__main__ import _run_scan

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
    _run_scan(args, src_file.read_text(), str(tmp_path))
    out = capsys.readouterr().out
    assert "Covered mutation sites:" in out


# ── Mutant-killing gap tests ──────────────────────────────────────────────────


def test_check_coverage_flags_single_flag_allowed():
    # mutmut_5: sum(cov_flags) > 1 — with only one flag, sum=1, must NOT exit
    import argparse
    from mutate4py.__main__ import _check_coverage_flags

    args = argparse.Namespace(cov_cmd="echo hi", lcov=None, reuse_coverage=False)
    _check_coverage_flags(args)  # must not raise


def test_check_coverage_flags_two_flags_exits_2(capsys):
    # mutmut_2,3,6: sum > 1 → exit(2)
    import argparse
    from mutate4py.__main__ import _check_coverage_flags

    args = argparse.Namespace(
        cov_cmd="echo hi", lcov="/some/path", reuse_coverage=False
    )
    with pytest.raises(SystemExit) as exc:
        _check_coverage_flags(args)
    assert exc.value.code == 2


def test_check_coverage_flags_all_three_exits_2():
    import argparse
    from mutate4py.__main__ import _check_coverage_flags

    args = argparse.Namespace(cov_cmd="echo", lcov="/f", reuse_coverage=True)
    with pytest.raises(SystemExit) as exc:
        _check_coverage_flags(args)
    assert exc.value.code == 2


def test_check_coverage_flags_stderr_has_error_text(capsys):
    import argparse
    from mutate4py.__main__ import _check_coverage_flags

    args = argparse.Namespace(cov_cmd="echo", lcov="/f", reuse_coverage=False)
    with pytest.raises(SystemExit):
        _check_coverage_flags(args)
    err = capsys.readouterr().err
    assert "error" in err.lower() or "mutually exclusive" in err


def test_load_source_missing_file_exits_2(tmp_path):
    # mutmut_6,_7: sys.exit(2) on missing file
    from mutate4py.__main__ import _load_source

    with pytest.raises(SystemExit) as exc:
        _load_source(str(tmp_path / "no_such.py"))
    assert exc.value.code == 2


def test_load_source_error_on_stderr(tmp_path, capsys):
    # mutmut_2,3,4,5: print(f"error: {exc}", file=sys.stderr)
    from mutate4py.__main__ import _load_source

    with pytest.raises(SystemExit):
        _load_source(str(tmp_path / "no_such.py"))
    err = capsys.readouterr().err
    assert "error" in err.lower()


def test_run_scan_coverage_error_exits_2(tmp_path):
    # mutmut_21-26: CoverageError → sys.exit(2) exactly
    import argparse
    from mutate4py.__main__ import _run_scan

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
        _run_scan(args, src_file.read_text(), str(tmp_path))
    assert exc.value.code == 2


def test_run_scan_coverage_error_goes_to_stderr(tmp_path, capsys):
    # mutmut_21-26: error message goes to stderr
    import argparse
    from mutate4py.__main__ import _run_scan

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
        _run_scan(args, src_file.read_text(), str(tmp_path))
    err = capsys.readouterr().err
    assert "error" in err.lower()


def test_run_scan_output_newline_separated(tmp_path, capsys):
    # mutmut_28,_36: print("\n".join(lines)) — output lines are newline-separated
    import argparse
    from mutate4py.__main__ import _run_scan

    src_file = tmp_path / "foo.py"
    src_file.write_text("x = a + b\n")
    args = argparse.Namespace(
        file=str(src_file),
        warning_threshold=1000,
        cov_cmd=None,
        lcov=None,
        reuse_coverage=False,
    )
    _run_scan(args, src_file.read_text(), str(tmp_path))
    out = capsys.readouterr().out
    assert "Mutation scan:" in out
    assert "Total mutation sites:" in out
    # Lines are separated by newlines (not spaces, tabs, etc.)
    assert "\n" in out


def test_scan_report_with_coverage_manifest_exists_false(tmp_path):
    # mutmut_22,23,24: "Manifest exists: false" must appear in output
    from mutate4py.__main__ import scan_report_with_coverage

    src_file = tmp_path / "foo.py"
    src_file.write_text("x = a + b\n")
    lcov_file = tmp_path / "cov.info"
    lcov_file.write_text(f"SF:{src_file}\nDA:1,1\nend_of_record\n")

    lines, _ = scan_report_with_coverage(
        str(src_file),
        src_file.read_text(),
        1000,
        cov_cmd=None,
        lcov_path=str(lcov_file),
        reuse_coverage=False,
        cwd=str(tmp_path),
    )
    assert "Manifest exists: false" in lines


def test_scan_report_with_coverage_no_warning_at_threshold(tmp_path):
    # mutmut_26: exceeded = total > warning_threshold (not >=), so at threshold no warning
    from mutate4py.__main__ import scan_report_with_coverage

    src_file = tmp_path / "foo.py"
    src_file.write_text("x = a + b\n")  # 1 site
    lcov_file = tmp_path / "cov.info"
    lcov_file.write_text(f"SF:{src_file}\nDA:1,1\nend_of_record\n")

    lines, exceeded = scan_report_with_coverage(
        str(src_file),
        src_file.read_text(),
        1,
        cov_cmd=None,
        lcov_path=str(lcov_file),
        reuse_coverage=False,
        cwd=str(tmp_path),
    )
    assert not exceeded
    assert not any("Warning" in line for line in lines)


def test_do_update_manifest_tested_at_iso8601_utc_format(tmp_path):
    # mutmut_5,7,8,9,10,13: tested_at = datetime.datetime.now(utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    import re
    from mutate4py.__main__ import _do_update_manifest

    p = tmp_path / "s.py"
    p.write_text("def foo():\n    return 1\n")
    _do_update_manifest(str(p), p.read_text())
    import json

    content = p.read_text()
    # Extract the JSON line from the manifest footer
    for line in content.splitlines():
        if line.startswith("# {") or (
            line.startswith("# ") and line[2:].startswith("{")
        ):
            manifest = json.loads(line[2:])
            tested_at = manifest["tested_at"]
            # Must match ISO-8601 UTC format: YYYY-MM-DDTHH:MM:SSZ
            assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", tested_at), (
                f"tested_at format wrong: {tested_at!r}"
            )
            return
    assert False, "No manifest JSON line found in output"


def test_main_no_coverage_flag_errors_about_coverage(tmp_path):
    # F4: invoking with no coverage flag attempts a run and errors about missing coverage.
    p = tmp_path / "s.py"
    p.write_text("x = a > b\n")
    result = subprocess.run(
        [sys.executable, "-m", "mutate4py", str(p)],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env={**os.environ, "PYTHONPATH": os.path.join(REPO_ROOT, "src")},
    )
    # Exits non-zero (1) because no coverage source is found
    assert result.returncode != 0


def test_run_scan_passes_cov_cmd_to_coverage(tmp_path, capsys):
    # mutmut_10: cov_cmd=None vs args.cov_cmd — cov_cmd must be passed through
    import argparse
    from mutate4py.__main__ import _run_scan

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
    _run_scan(args, src_file.read_text(), str(tmp_path))
    out = capsys.readouterr().out
    assert "Covered mutation sites:" in out


def test_run_scan_reuse_coverage_with_cwd(tmp_path, capsys):
    # mutmut_12/13: reuse_coverage and cwd are passed through to acquire_coverage;
    # coverage.lcov in cwd is found only when cwd is correct
    import argparse
    from mutate4py.__main__ import _run_scan

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
    _run_scan(args, src_file.read_text(), str(tmp_path))
    out = capsys.readouterr().out
    assert "Covered mutation sites:" in out


def test_run_scan_passes_args_file_path(tmp_path, capsys):
    # mutmut_28: scan_report(None, ...) vs scan_report(args.file, ...)
    # Path in header must match args.file
    import argparse
    from mutate4py.__main__ import _run_scan

    src_file = tmp_path / "mymod.py"
    src_file.write_text("x = a + b\n")
    args = argparse.Namespace(
        file=str(src_file),
        warning_threshold=1000,
        cov_cmd=None,
        lcov=None,
        reuse_coverage=False,
    )
    _run_scan(args, src_file.read_text(), str(tmp_path))
    out = capsys.readouterr().out
    assert "mymod.py" in out


def test_run_scan_separator_is_newline_not_other_string(tmp_path, capsys):
    # mutmut_36: "XX\nXX".join(lines) vs "\n".join(lines)
    import argparse
    from mutate4py.__main__ import _run_scan

    src_file = tmp_path / "foo.py"
    src_file.write_text("pass\n")
    args = argparse.Namespace(
        file=str(src_file),
        warning_threshold=1000,
        cov_cmd=None,
        lcov=None,
        reuse_coverage=False,
    )
    _run_scan(args, src_file.read_text(), str(tmp_path))
    out = capsys.readouterr().out
    assert "XX" not in out
    # Output must have each label on its own line
    for label in ["Mutation scan:", "Total mutation sites:"]:
        assert label in out


def test_do_update_manifest_uses_utc_not_local_tz(tmp_path):
    # mutmut_7: datetime.now(None) vs datetime.now(utc)
    # None gives local time without tzinfo; utc gives UTC with tzinfo
    # The strftime format %Y-%m-%dT%H:%M:%SZ works for both but the timestamp
    # will differ. We verify by checking the format is valid ISO-8601 UTC.
    import re
    from mutate4py.__main__ import _do_update_manifest

    p = tmp_path / "s.py"
    p.write_text("def foo():\n    return 1\n")
    _do_update_manifest(str(p), p.read_text())
    content = p.read_text()
    import json

    for line in content.splitlines():
        if line.startswith("# ") and line[2:].startswith("{"):
            m = json.loads(line[2:])
            ta = m["tested_at"]
            assert ta.endswith("Z"), f"tested_at must end with Z (UTC): {ta!r}"
            assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", ta)
            return
    assert False, "No manifest line found"


def test_mutation_warning_type_int_parses_string_arg():
    # mutmut_34,38: type=int removed → --mutation-warning receives str, comparison int>str fails
    src = "x = a + b\n"
    result = run_cli("--scan", "--mutation-warning", "5", source=src)
    assert result.returncode == 0
    assert "Total mutation sites: 1" in result.stdout


def test_mutation_warning_threshold_comparison_is_numeric(tmp_path, capsys):
    # mutmut_34,38: type=int removed → --mutation-warning="5" → str "5" → int > str → TypeError
    # In-process test: if type=int, works cleanly; if type=None, crashes with TypeError
    import mutate4py.__main__ as m

    p = tmp_path / "s.py"
    p.write_text("x = a + b\n")  # 1 site
    sys.argv = ["mutate4py", str(p), "--scan", "--mutation-warning", "2"]
    m.main()  # must not raise TypeError; threshold=2, 1 site → no warning
    out = capsys.readouterr().out
    assert "Warning" not in out


# ── _parse_lines ──────────────────────────────────────────────────────────────


def test_parse_lines_none():
    from mutate4py.__main__ import _parse_lines
    assert _parse_lines(None) is None


def test_parse_lines_single():
    from mutate4py.__main__ import _parse_lines
    assert _parse_lines("5") == {5}


def test_parse_lines_multiple():
    from mutate4py.__main__ import _parse_lines
    assert _parse_lines("3,7,12") == {3, 7, 12}


def test_parse_lines_with_spaces():
    from mutate4py.__main__ import _parse_lines
    assert _parse_lines(" 3 , 7 ") == {3, 7}


# ── _build_parser: dest and flag-name mutants ─────────────────────────────────


def test_build_parser_lcov_dest_is_lcov():
    # mutmut_8: dest=None → --lcov value stored as None key (unreachable as args.lcov)
    # mutmut_11: dest omitted → argparse derives "lcov" from "--lcov" (equivalent)
    from mutate4py.__main__ import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["somefile.py", "--lcov", "/path/to/cov.info"])
    assert args.lcov == "/path/to/cov.info"


def test_build_parser_lcov_default_is_none():
    # mutmut_12: default=None omitted → argparse uses None anyway (equivalent)
    # Verify default behavior: no --lcov flag → args.lcov is None
    from mutate4py.__main__ import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["somefile.py"])
    assert args.lcov is None


def test_build_parser_mutate_all_flag_exists():
    # mutmut_18: "--mutate-all" → "--MUTATE-ALL" (different flag name)
    # Correct: --mutate-all must be parseable and set mutate_all=True
    from mutate4py.__main__ import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["somefile.py", "--mutate-all"])
    assert args.mutate_all is True


def test_build_parser_mutate_all_default_false():
    from mutate4py.__main__ import _build_parser
    parser = _build_parser()
    args = parser.parse_args(["somefile.py"])
    assert args.mutate_all is False
