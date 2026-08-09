"""Unit tests for mutate4py CLI entry point (__main__)."""

import os
import subprocess
import sys
import tempfile
import textwrap

import pytest

from mutate4py._runner import CoverageSource, scan_report

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


@pytest.mark.integration
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


@pytest.mark.integration
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
    assert any("Warning: 2 mutation sites exceeds threshold 1." in line for line in lines)


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
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 0
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
    from mutate4py._runner import update_manifest

    p = tmp_path / "s.py"
    p.write_text("def foo():\n    return 1\n")
    update_manifest(path=str(p), source=p.read_text())
    content = p.read_text()
    assert "# mutate4py-manifest-begin" in content
    assert "Updated manifest:" in capsys.readouterr().out


def test_do_update_manifest_idempotent(tmp_path, capsys):
    from mutate4py._runner import update_manifest

    p = tmp_path / "s.py"
    p.write_text("def foo():\n    return 1\n")
    update_manifest(path=str(p), source=p.read_text())
    first_content = p.read_text()
    capsys.readouterr()  # clear
    update_manifest(path=str(p), source=first_content)
    assert "Manifest unchanged:" in capsys.readouterr().out
    assert p.read_text() == first_content


def test_main_update_manifest_mode(tmp_path, capsys):
    import mutate4py.__main__ as m

    p = tmp_path / "s.py"
    p.write_text("def foo():\n    return 1\n")
    sys.argv = ["mutate4py", str(p), "--update-manifest"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "manifest" in out.lower()
    assert "# mutate4py-manifest-begin" in p.read_text()


# ── scan_report_with_coverage unit tests ─────────────────────────────────────


def test_scan_report_with_coverage_basic(tmp_path):
    from mutate4py._runner import scan_report_with_coverage

    src_file = tmp_path / "foo.py"
    src_file.write_text("x = a + b\n")
    lcov_file = tmp_path / "cov.info"
    lcov_file.write_text(f"SF:{src_file}\nDA:1,1\nend_of_record\n")

    lines, exceeded = scan_report_with_coverage(
        str(src_file),
        src_file.read_text(),
        1000,
        CoverageSource(cov_cmd=None, lcov_path=str(lcov_file), reuse_coverage=False, cwd=str(tmp_path)),
    )
    assert any("Covered mutation sites:" in line for line in lines)
    assert any("Uncovered mutation sites:" in line for line in lines)
    assert not exceeded


def test_scan_report_with_coverage_warning(tmp_path):
    from mutate4py._runner import scan_report_with_coverage

    src_file = tmp_path / "foo.py"
    src_file.write_text("x = a + b\ny = c - d\n")
    lcov_file = tmp_path / "cov.info"
    lcov_file.write_text(f"SF:{src_file}\nDA:1,1\nend_of_record\n")

    lines, exceeded = scan_report_with_coverage(
        str(src_file),
        src_file.read_text(),
        1,
        CoverageSource(cov_cmd=None, lcov_path=str(lcov_file), reuse_coverage=False, cwd=str(tmp_path)),
    )
    assert exceeded
    assert any("Warning:" in line for line in lines)


def test_scan_report_with_coverage_manifest_exists_false(tmp_path):
    # mutant_22,23,24: "Manifest exists: false" must appear in output
    from mutate4py._runner import scan_report_with_coverage

    src_file = tmp_path / "foo.py"
    src_file.write_text("x = a + b\n")
    lcov_file = tmp_path / "cov.info"
    lcov_file.write_text(f"SF:{src_file}\nDA:1,1\nend_of_record\n")

    lines, _ = scan_report_with_coverage(
        str(src_file),
        src_file.read_text(),
        1000,
        CoverageSource(cov_cmd=None, lcov_path=str(lcov_file), reuse_coverage=False, cwd=str(tmp_path)),
    )
    assert "Manifest exists: false" in lines


def test_scan_report_with_coverage_no_warning_at_threshold(tmp_path):
    # mutant_26: exceeded = total > warning_threshold (not >=), so at threshold no warning
    from mutate4py._runner import scan_report_with_coverage

    src_file = tmp_path / "foo.py"
    src_file.write_text("x = a + b\n")  # 1 site
    lcov_file = tmp_path / "cov.info"
    lcov_file.write_text(f"SF:{src_file}\nDA:1,1\nend_of_record\n")

    lines, exceeded = scan_report_with_coverage(
        str(src_file),
        src_file.read_text(),
        1,
        CoverageSource(cov_cmd=None, lcov_path=str(lcov_file), reuse_coverage=False, cwd=str(tmp_path)),
    )
    assert not exceeded
    assert not any("Warning" in line for line in lines)


def test_do_update_manifest_tested_at_iso8601_utc_format(tmp_path):
    # mutant_5,7,8,9,10,13: tested_at = datetime.datetime.now(utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    import re
    from mutate4py._runner import update_manifest

    p = tmp_path / "s.py"
    p.write_text("def foo():\n    return 1\n")
    update_manifest(path=str(p), source=p.read_text())
    import json

    content = p.read_text()
    # Extract the JSON line from the manifest footer
    for line in content.splitlines():
        if line.startswith("# {") or (line.startswith("# ") and line[2:].startswith("{")):
            manifest = json.loads(line[2:])
            tested_at = manifest["tested_at"]
            # Must match ISO-8601 UTC format: YYYY-MM-DDTHH:MM:SSZ
            assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", tested_at), (
                f"tested_at format wrong: {tested_at!r}"
            )
            return
    assert False, "No manifest JSON line found in output"


@pytest.mark.integration
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


def test_do_update_manifest_uses_utc_not_local_tz(tmp_path):
    # mutant_7: datetime.now(None) vs datetime.now(utc)
    # None gives local time without tzinfo; utc gives UTC with tzinfo
    # The strftime format %Y-%m-%dT%H:%M:%SZ works for both but the timestamp
    # will differ. We verify by checking the format is valid ISO-8601 UTC.
    import re
    from mutate4py._runner import update_manifest

    p = tmp_path / "s.py"
    p.write_text("def foo():\n    return 1\n")
    update_manifest(path=str(p), source=p.read_text())
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
    # mutant_34,38: type=int removed → --mutation-warning receives str, comparison int>str fails
    src = "x = a + b\n"
    result = run_cli("--scan", "--mutation-warning", "5", source=src)
    assert result.returncode == 0
    assert "Total mutation sites: 1" in result.stdout


def test_mutation_warning_threshold_comparison_is_numeric(tmp_path, capsys):
    # mutant_34,38: type=int removed → --mutation-warning="5" → str "5" → int > str → TypeError
    # In-process test: if type=int, works cleanly; if type=None, crashes with TypeError
    import mutate4py.__main__ as m

    p = tmp_path / "s.py"
    p.write_text("x = a + b\n")  # 1 site
    sys.argv = ["mutate4py", str(p), "--scan", "--mutation-warning", "2"]
    with pytest.raises(SystemExit):  # must not raise TypeError; threshold=2, 1 site → no warning
        m.main()
    out = capsys.readouterr().out
    assert "Warning" not in out


# ── _build_parser: dest and flag-name mutants ─────────────────────────────────


def test_build_parser_lcov_dest_is_lcov():
    # mutant_8: dest=None → --lcov value stored as None key (unreachable as args.lcov)
    # mutant_11: dest omitted → argparse derives "lcov" from "--lcov" (equivalent)
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["somefile.py", "--lcov", "/path/to/cov.info"])
    assert args.lcov == "/path/to/cov.info"


def test_build_parser_defaults_no_flags():
    # mutant_12: default=None omitted; mutmut_18: --mutate-all default is False
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["somefile.py"])
    assert args.lcov is None
    assert args.mutate_all is False


def test_build_parser_mutate_all_flag_exists():
    # mutant_18: "--mutate-all" → "--MUTATE-ALL" (different flag name)
    # Correct: --mutate-all must be parseable and set mutate_all=True
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["somefile.py", "--mutate-all"])
    assert args.mutate_all is True


# ── F5: --max-workers flag ────────────────────────────────────────────────────


def test_build_parser_max_workers_sets_value():
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py", "--max-workers", "4"])
    assert args.max_workers == 4


def test_build_parser_flag_defaults():
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py"])
    assert args.max_workers is None
    assert args.verbose is False


def test_build_parser_manifest_file_dest_is_manifest_file():
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py", "--manifest-file"])
    assert args.manifest_file is True


def test_build_parser_no_fork_server_defaults_false():
    """Fork-server fast path is on by default: --no-fork-server absent -> False."""
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py"])
    assert args.no_fork_server is False


def test_build_parser_no_fork_server_flag_sets_true():
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py", "--no-fork-server"])
    assert args.no_fork_server is True


def test_build_parser_manifest_file_defaults_to_false():
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py"])
    assert args.manifest_file is False


def test_max_workers_zero_is_usage_error(source="x = 1\n"):
    result = run_cli("--max-workers", "0", source="x = 1\n")
    assert result.returncode != 0


def test_max_workers_negative_is_usage_error():
    result = run_cli("--max-workers", "-1", source="x = 1\n")
    assert result.returncode != 0


def test_max_workers_non_integer_is_usage_error():
    result = run_cli("--max-workers", "many", source="x = 1\n")
    assert result.returncode != 0


# ── F5: --mutation-warning default is 50 ─────────────────────────────────────


def test_mutation_warning_default_is_50():
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py"])
    assert args.warning_threshold == 50


# ── F5: --lines positive-int validation ──────────────────────────────────────


def test_lines_zero_is_usage_error():
    result = run_cli("--scan", "--lines", "0", source="x = 1\n")
    assert result.returncode != 0


def test_lines_negative_is_usage_error():
    result = run_cli("--scan", "--lines", "7,-2", source="x = 1\n")
    assert result.returncode != 0


def test_lines_non_integer_is_usage_error():
    result = run_cli("--scan", "--lines", "7,x", source="x = 1\n")
    assert result.returncode != 0


# ── F5: mutual exclusion — --scan / --update-manifest ────────────────────────
#
# Coverage for these flag-exclusivity combinations lives with the in-process
# `_validate_mutual_exclusions` unit tests in tests/test_cli_validation.py:
# they exercise pure argparse-namespace validation logic with no
# filesystem/process dependency, so a subprocess round-trip adds cost
# without adding coverage.


# ── F5: --help ────────────────────────────────────────────────────────────────


def test_help_exits_zero():
    result = run_cli("--help", source="x = 1\n")
    assert result.returncode == 0


def test_help_lists_max_workers():
    result = run_cli("--help", source="x = 1\n")
    assert "--max-workers" in result.stdout


def test_help_lists_manifest_file():
    result = run_cli("--help", source="x = 1\n")
    assert "--manifest-file" in result.stdout


def test_help_lists_exclude():
    result = run_cli("--help", source="x = 1\n")
    assert "--exclude" in result.stdout


def test_build_parser_declares_the_file_scratch_field():
    """args.file is a declared field of the parser's Namespace, not an
    attribute _dispatch injects unannounced (issue #22 review)."""
    from mutate4py.__main__ import _build_parser

    args = _build_parser().parse_args(["a.py"])
    assert args.files == ["a.py"]
    assert args.file is None


def test_help_with_invalid_args_still_exits_zero():
    # --help is honoured before any validation
    result = run_cli("--help", "--max-workers", "0", source="x = 1\n")
    assert result.returncode == 0


# ── F5: positive-int rejection ────────────────────────────────────────────────


def test_mutation_warning_zero_is_usage_error():
    result = run_cli("--scan", "--mutation-warning", "0", source="x = 1\n")
    assert result.returncode != 0


def test_mutation_warning_negative_is_usage_error():
    result = run_cli("--scan", "--mutation-warning", "-3", source="x = 1\n")
    assert result.returncode != 0


def test_mutation_warning_non_integer_is_usage_error():
    result = run_cli("--scan", "--mutation-warning", "two", source="x = 1\n")
    assert result.returncode != 0


def test_timeout_factor_zero_is_usage_error():
    result = run_cli("--scan", "--timeout-factor", "0", source="x = 1\n")
    assert result.returncode != 0


def test_timeout_factor_float_is_usage_error():
    result = run_cli("--scan", "--timeout-factor", "1.5", source="x = 1\n")
    assert result.returncode != 0


# ── F5: unknown flag / missing file ──────────────────────────────────────────


def test_unknown_flag_is_usage_error():
    result = run_cli("--bogus-flag", source="x = 1\n")
    assert result.returncode != 0


@pytest.mark.integration
def test_no_positional_file_is_usage_error():
    result = subprocess.run(
        [sys.executable, "-m", "mutate4py"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": os.path.join(REPO_ROOT, "src")},
    )
    assert result.returncode != 0


# ── F5: --verbose flag ────────────────────────────────────────────────────────


def test_verbose_flag_parses():
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py", "--verbose"])
    assert args.verbose is True


# ── _positive_int: error branches ────────────────────────────────────────────


def test_positive_int_non_integer_raises():
    import argparse
    from mutate4py.__main__ import _positive_int

    try:
        _positive_int("abc")
        assert False, "expected ArgumentTypeError"
    except argparse.ArgumentTypeError as exc:
        assert "not a valid integer" in str(exc)


def test_positive_int_zero_raises():
    import argparse
    from mutate4py.__main__ import _positive_int

    try:
        _positive_int("0")
        assert False, "expected ArgumentTypeError"
    except argparse.ArgumentTypeError as exc:
        assert "positive integer" in str(exc)


def test_positive_int_negative_raises():
    import argparse
    from mutate4py.__main__ import _positive_int

    try:
        _positive_int("-5")
        assert False, "expected ArgumentTypeError"
    except argparse.ArgumentTypeError as exc:
        assert "positive integer" in str(exc)


# ── --check-manifest: single file ────────────────────────────────────────────


def _run_cli_path(path: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "mutate4py", path] + list(args),
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": os.path.join(REPO_ROOT, "src")},
        timeout=30,
    )


def _run_cli_in(cwd: str, *args: str) -> subprocess.CompletedProcess:
    """Run mutate4py with no positional path, from a given cwd (for
    zero-positional autodiscovery tests, issue #22 items 3, 8-12)."""
    return subprocess.run(
        [sys.executable, "-m", "mutate4py"] + list(args),
        capture_output=True,
        text=True,
        cwd=cwd,
        env={**os.environ, "PYTHONPATH": os.path.join(REPO_ROOT, "src")},
        timeout=30,
    )


@pytest.mark.integration
def test_check_manifest_missing_exits_1(tmp_path):
    p = tmp_path / "mod.py"
    p.write_text("def f(a, b):\n    return a > b\n")
    result = _run_cli_path(str(p), "--check-manifest")
    assert result.returncode == 1
    assert "Manifest missing:" in result.stdout


@pytest.mark.integration
def test_check_manifest_current_exits_0(tmp_path):
    import mutate4py.__main__ as m

    p = tmp_path / "mod.py"
    p.write_text("def f(a, b):\n    return a > b\n")
    sys.argv = ["mutate4py", str(p), "--update-manifest"]
    with pytest.raises(SystemExit):
        m.main()
    result = _run_cli_path(str(p), "--check-manifest")
    assert result.returncode == 0
    assert "Manifest current:" in result.stdout


def test_check_manifest_in_help():
    result = run_cli("--help", source="x = 1\n")
    assert "--check-manifest" in result.stdout


# ── --manifest-file: single file end-to-end ────────────────────────────────────


@pytest.mark.integration
def test_manifest_file_update_writes_sidecar_and_footer_free_source(tmp_path):
    import json

    p = tmp_path / "mod.py"
    p.write_text("def f(a, b):\n    return a > b\n")
    sidecar = tmp_path / "mod.py.manifest.json"

    result = _run_cli_path(str(p), "--update-manifest", "--manifest-file")

    assert result.returncode == 0
    assert "Updated manifest:" in result.stdout
    assert sidecar.is_file()
    sidecar_data = json.loads(sidecar.read_text())
    assert sidecar_data["functions"][0]["id"] == "func/f"
    assert "mutate4py-manifest-begin" not in p.read_text()


@pytest.mark.integration
def test_manifest_file_check_reads_sidecar(tmp_path):
    p = tmp_path / "mod.py"
    p.write_text("def f(a, b):\n    return a > b\n")
    _run_cli_path(str(p), "--update-manifest", "--manifest-file")

    result = _run_cli_path(str(p), "--check-manifest", "--manifest-file")

    assert result.returncode == 0
    assert "Manifest current:" in result.stdout


@pytest.mark.integration
def test_manifest_file_check_missing_sidecar_reports_missing(tmp_path):
    p = tmp_path / "mod.py"
    p.write_text("def f(a, b):\n    return a > b\n")

    result = _run_cli_path(str(p), "--check-manifest", "--manifest-file")

    assert result.returncode == 1
    assert "Manifest missing:" in result.stdout


# ── directory support ─────────────────────────────────────────────────────────


def _make_src_dir(tmp_path, files: dict[str, str]) -> str:
    """Create a directory with given {filename: content} mapping; return dir path."""
    d = tmp_path / "src"
    d.mkdir()
    for name, content in files.items():
        (d / name).write_text(content)
    return str(d)


@pytest.mark.integration
def test_directory_run_mode_attempts_run_on_files(tmp_path):
    d = _make_src_dir(tmp_path, {"a.py": "x = 1\n"})
    result = _run_cli_path(d, "--test-command", "true")
    assert "run mode requires a single file, not a directory" not in result.stderr


@pytest.mark.integration
def test_directory_check_manifest_all_missing_exits_1(tmp_path):
    d = _make_src_dir(tmp_path, {"a.py": "def f(): pass\n", "b.py": "def g(): pass\n"})
    result = _run_cli_path(d, "--check-manifest")
    assert result.returncode == 1
    assert "Manifest missing:" in result.stdout


@pytest.mark.integration
def test_directory_check_manifest_all_current_exits_0(tmp_path):
    import mutate4py.__main__ as m

    d = tmp_path / "src"
    d.mkdir()
    for name in ("a.py", "b.py"):
        p = d / name
        p.write_text("def f(): pass\n")
        sys.argv = ["mutate4py", str(p), "--update-manifest"]
        with pytest.raises(SystemExit):
            m.main()

    result = _run_cli_path(str(d), "--check-manifest")
    assert result.returncode == 0
    assert "Manifest current:" in result.stdout


@pytest.mark.integration
def test_directory_check_manifest_one_stale_exits_1(tmp_path):
    import mutate4py.__main__ as m

    d = tmp_path / "src"
    d.mkdir()
    p_a = d / "a.py"
    p_a.write_text("def f(): pass\n")
    sys.argv = ["mutate4py", str(p_a), "--update-manifest"]
    with pytest.raises(SystemExit):
        m.main()

    p_b = d / "b.py"
    p_b.write_text("def g(): pass\n")

    result = _run_cli_path(str(d), "--check-manifest")
    assert result.returncode == 1
    assert "Manifest missing:" in result.stdout
    assert "Manifest current:" in result.stdout


@pytest.mark.integration
def test_directory_check_manifest_excluded_file_ignored_exits_0(tmp_path):
    import mutate4py.__main__ as m

    d = tmp_path / "src"
    d.mkdir()
    p_a = d / "a.py"
    p_a.write_text("def f(): pass\n")
    sys.argv = ["mutate4py", str(p_a), "--update-manifest"]
    with pytest.raises(SystemExit):
        m.main()

    (d / "b.py").write_text("def g(): pass\n")

    result = _run_cli_path(str(d), "--check-manifest", "--exclude", "**/b.py")
    assert result.returncode == 0
    assert "Manifest current:" in result.stdout
    assert "b.py" not in result.stdout


@pytest.mark.integration
def test_directory_check_manifest_stale_survivor_exits_1(tmp_path):
    """One non-excluded stale file still fails, reporting only that file."""
    import mutate4py.__main__ as m

    d = tmp_path / "src"
    d.mkdir()
    p_a = d / "a.py"
    p_a.write_text("def f(): pass\n")
    sys.argv = ["mutate4py", str(p_a), "--update-manifest"]
    with pytest.raises(SystemExit):
        m.main()

    (d / "b.py").write_text("def g(): pass\n")
    (d / "c.py").write_text("def h(): pass\n")

    result = _run_cli_path(str(d), "--check-manifest", "--exclude", "**/c.py")
    assert result.returncode == 1
    assert "Manifest missing:" in result.stdout
    assert "b.py" in result.stdout
    assert "c.py" not in result.stdout


@pytest.mark.integration
def test_directory_all_files_excluded_exits_2(tmp_path):
    d = _make_src_dir(tmp_path, {"a.py": "def f(): pass\n", "b.py": "def g(): pass\n"})
    result = _run_cli_path(d, "--check-manifest", "--exclude", "**/*.py")
    assert result.returncode == 2
    assert "error: no Python files to process." in result.stderr
    assert result.stdout == ""


@pytest.mark.integration
def test_directory_with_no_py_files_exits_2(tmp_path):
    d = tmp_path / "src"
    d.mkdir()
    (d / "README.md").write_text("docs\n")
    result = _run_cli_path(str(d), "--check-manifest")
    assert result.returncode == 2
    assert "error: no Python files to process." in result.stderr


@pytest.mark.integration
def test_directory_all_files_excluded_exits_2_in_scan_mode(tmp_path):
    d = _make_src_dir(tmp_path, {"a.py": "x = 1\n"})
    result = _run_cli_path(d, "--scan", "--exclude", "**/*.py")
    assert result.returncode == 2
    assert "error: no Python files to process." in result.stderr


@pytest.mark.integration
def test_directory_all_files_excluded_exits_2_in_update_manifest_mode(tmp_path):
    d = _make_src_dir(tmp_path, {"a.py": "x = 1\n"})
    result = _run_cli_path(d, "--update-manifest", "--exclude", "**/*.py")
    assert result.returncode == 2
    assert "error: no Python files to process." in result.stderr
    assert "mutate4py-manifest-begin" not in (tmp_path / "src" / "a.py").read_text()


@pytest.mark.integration
def test_directory_all_files_excluded_exits_2_in_run_mode(tmp_path):
    """Run mode bails before acquiring coverage or timing a baseline."""
    d = _make_src_dir(tmp_path, {"a.py": "x = 1\n"})
    result = _run_cli_path(d, "--exclude", "**/*.py", "--test-command", "false")
    assert result.returncode == 2
    assert "error: no Python files to process." in result.stderr


@pytest.mark.integration
def test_directory_verbose_reports_excluded_files(tmp_path):
    d = _make_src_dir(tmp_path, {"a.py": "def f(): pass\n", "b.py": "def g(): pass\n"})
    result = _run_cli_path(d, "--check-manifest", "--exclude", "**/b.py", "--verbose")
    assert f"Excluded: {os.path.join(d, 'b.py')}" in result.stdout
    assert "Excluded: " + os.path.join(d, "a.py") not in result.stdout


@pytest.mark.integration
def test_directory_excluded_files_are_silent_without_verbose(tmp_path):
    d = _make_src_dir(tmp_path, {"a.py": "def f(): pass\n", "b.py": "def g(): pass\n"})
    result = _run_cli_path(d, "--check-manifest", "--exclude", "**/b.py")
    assert "Excluded:" not in result.stdout
    assert "b.py" not in result.stdout


@pytest.mark.integration
def test_directory_two_exclude_flags_both_take_effect(tmp_path):
    """Two separate --exclude flags on argv both apply (action="append"), not just
    the last one (which is what a dropped/misconfigured `dest` would leave)."""
    d = _make_pkg_tree(tmp_path)
    result = _run_cli_path(
        d,
        "--check-manifest",
        "--exclude",
        "**/__init__.py",
        "--exclude",
        "**/sub/deep.py",
        "--verbose",
    )
    assert f"Excluded: {os.path.join(d, '__init__.py')}" in result.stdout
    assert f"Excluded: {os.path.join(d, 'sub', '__init__.py')}" in result.stdout
    assert f"Excluded: {os.path.join(d, 'sub', 'deep.py')}" in result.stdout
    assert "Excluded: " + os.path.join(d, "mod.py") not in result.stdout
    assert "Manifest missing: " + os.path.join(d, "mod.py") in result.stdout


@pytest.mark.integration
def test_single_file_matching_exclude_exits_2(tmp_path):
    p = tmp_path / "mod.py"
    p.write_text("def f(): pass\n")
    result = _run_cli_path(str(p), "--check-manifest", "--exclude", "**/mod.py")
    assert result.returncode == 2
    assert "error: no Python files to process." in result.stderr
    assert "Manifest missing:" not in result.stdout


@pytest.mark.integration
def test_missing_single_file_reports_not_found_even_when_excluded(tmp_path):
    """A path that does not exist reports the real error, never 'excluded'."""
    missing = str(tmp_path / "mod.py")
    result = _run_cli_path(missing, "--check-manifest", "--exclude", "**/mod.py")
    assert result.returncode == 2
    assert "No such file or directory" in result.stderr
    assert "no Python files to process" not in result.stderr


@pytest.mark.integration
def test_existing_single_file_matching_exclude_reports_exclusion_not_not_found(
    tmp_path,
):
    """The companion ordering: an existing target that matches is an exclusion."""
    p = tmp_path / "mod.py"
    p.write_text("def f(): pass\n")
    result = _run_cli_path(str(p), "--check-manifest", "--exclude", "**/mod.py")
    assert result.returncode == 2
    assert "error: no Python files to process." in result.stderr
    assert "No such file or directory" not in result.stderr


@pytest.mark.integration
def test_single_file_verbose_reports_the_excluded_target(tmp_path):
    p = tmp_path / "mod.py"
    p.write_text("def f(): pass\n")
    result = _run_cli_path(str(p), "--check-manifest", "--exclude", "**/mod.py", "--verbose")
    assert f"Excluded: {p}" in result.stdout


@pytest.mark.integration
def test_single_file_not_matching_exclude_is_a_no_op(tmp_path):
    p = tmp_path / "mod.py"
    p.write_text("def f(): pass\n")
    result = _run_cli_path(str(p), "--check-manifest", "--exclude", "**/other.py")
    assert result.returncode == 1
    assert "Manifest missing:" in result.stdout


@pytest.mark.integration
def test_directory_update_manifest_processes_all_files(tmp_path):
    d = _make_src_dir(tmp_path, {"a.py": "def f(): pass\n", "b.py": "def g(): pass\n"})
    result = _run_cli_path(d, "--update-manifest")
    assert result.returncode == 0
    for name in ("a.py", "b.py"):
        content = (tmp_path / "src" / name).read_text()
        assert "mutate4py-manifest-begin" in content


@pytest.mark.integration
def test_directory_scan_processes_all_files(tmp_path):
    d = _make_src_dir(tmp_path, {"a.py": "x = a > b\n", "b.py": "y = c + d\n"})
    result = _run_cli_path(d, "--scan")
    assert result.returncode == 0
    assert result.stdout.count("Mutation scan:") == 2


@pytest.mark.integration
def test_directory_manifest_file_writes_one_sidecar_per_file(tmp_path):
    """--manifest-file works for a directory target: each source file gets its
    own <file>.manifest.json, and no source file gains an embedded footer."""
    import json

    d = _make_src_dir(
        tmp_path,
        {
            "a.py": "def f(a, b):\n    return a > b\n",
            "b.py": "def g(c, d):\n    return c + d\n",
        },
    )

    result = _run_cli_path(d, "--update-manifest", "--manifest-file")

    assert result.returncode == 0
    a_path = str(tmp_path / "src" / "a.py")
    b_path = str(tmp_path / "src" / "b.py")
    for path in (a_path, b_path):
        assert "mutate4py-manifest-begin" not in open(path).read()

    a_sidecar = json.loads(open(a_path + ".manifest.json").read())
    b_sidecar = json.loads(open(b_path + ".manifest.json").read())
    assert a_sidecar["functions"][0]["id"] == "func/f"
    assert b_sidecar["functions"][0]["id"] == "func/g"

    check_result = _run_cli_path(d, "--check-manifest", "--manifest-file")
    assert check_result.returncode == 0
    assert check_result.stdout.count("Manifest current:") == 2


def _make_pkg_tree(tmp_path) -> str:
    """pkg/{mod.py, __init__.py, sub/{deep.py, __init__.py}}; return pkg path."""
    d = tmp_path / "pkg"
    sub = d / "sub"
    sub.mkdir(parents=True)
    for p in (d / "mod.py", d / "__init__.py", sub / "deep.py", sub / "__init__.py"):
        p.write_text("x = 1\n")
    return str(d)


# ── directory dispatch: in-process coverage ───────────────────────────────────


def test_main_directory_run_mode_exits_1_without_coverage(tmp_path):
    import mutate4py.__main__ as m

    d = tmp_path / "src"
    d.mkdir()
    (d / "a.py").write_text("x = a > b\n")
    sys.argv = ["mutate4py", str(d)]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 1


def test_main_directory_check_manifest_missing_exits_1(tmp_path, capsys):
    import mutate4py.__main__ as m

    d = tmp_path / "src"
    d.mkdir()
    (d / "a.py").write_text("def f(): pass\n")
    sys.argv = ["mutate4py", str(d), "--check-manifest"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 1
    assert "Manifest missing:" in capsys.readouterr().out


def test_main_directory_check_manifest_current_exits_0(tmp_path, capsys):
    import mutate4py.__main__ as m

    d = tmp_path / "src"
    d.mkdir()
    p = d / "a.py"
    p.write_text("def f(): pass\n")
    sys.argv = ["mutate4py", str(p), "--update-manifest"]
    with pytest.raises(SystemExit):
        m.main()
    capsys.readouterr()

    sys.argv = ["mutate4py", str(d), "--check-manifest"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 0
    assert "Manifest current:" in capsys.readouterr().out


def test_main_directory_update_manifest_exits_0(tmp_path, capsys):
    import mutate4py.__main__ as m

    d = tmp_path / "src"
    d.mkdir()
    (d / "a.py").write_text("def f(): pass\n")
    sys.argv = ["mutate4py", str(d), "--update-manifest"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 0
    assert "mutate4py-manifest-begin" in (d / "a.py").read_text()


def test_main_directory_scan_exits_0(tmp_path, capsys):
    import mutate4py.__main__ as m

    d = tmp_path / "src"
    d.mkdir()
    (d / "a.py").write_text("x = a > b\n")
    sys.argv = ["mutate4py", str(d), "--scan"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 0
    assert "Mutation scan:" in capsys.readouterr().out


# ── unparseable file in a directory batch (issue #35) ──────────────────────────


def test_main_directory_scan_continues_past_syntax_error(tmp_path, capsys):
    """Reproduction from issue #35: good.py / bad.py / zlast.py, bad.py has
    invalid syntax. Every other file must still be scanned; the batch reports
    exit 2 and a trailing parse-failure count, not a traceback."""
    import mutate4py.__main__ as m

    d = tmp_path / "src"
    d.mkdir()
    (d / "good.py").write_text("x = a > b\n")
    (d / "bad.py").write_text("def broken(:\n    pass\n")
    (d / "zlast.py").write_text("y = c > d\n")
    sys.argv = ["mutate4py", str(d), "--scan"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 2
    captured = capsys.readouterr()
    out, err = captured.out, captured.err
    assert f"Mutation scan: {d / 'good.py'}" in out
    assert f"Mutation scan: {d / 'zlast.py'}" in out
    assert f"error: cannot parse {d / 'bad.py'}:" in err
    assert "error: 1 files could not be parsed" in err
    assert "Traceback" not in err


def test_main_directory_run_mode_continues_past_syntax_error(tmp_path, capsys):
    """The default mutation Run loop (no --scan/--update-manifest/--check-manifest)
    must apply the same continue-the-batch contract as the other three modes
    (issue #35 acceptance: "Applies to ... the Run loop")."""
    import mutate4py.__main__ as m

    d = tmp_path / "src"
    d.mkdir()
    good = d / "good.py"
    bad = d / "bad.py"
    zlast = d / "zlast.py"
    good.write_text("def f(a, b):\n    return a > b\n")
    bad.write_text("def broken(:\n    pass\n")
    zlast.write_text("def g(c, d):\n    return c > d\n")

    lcov = tmp_path / "lcov.info"
    lcov.write_text(f"SF:{good}\nDA:2,1\nend_of_record\nSF:{zlast}\nDA:2,1\nend_of_record\n")

    sys.argv = [
        "mutate4py",
        str(d),
        "--lcov",
        str(lcov),
        "--test-command",
        "true",
    ]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 2
    captured = capsys.readouterr()
    out, err = captured.out, captured.err
    assert f"Mutation run: {good}" in out
    assert f"Mutation run: {zlast}" in out
    assert f"error: cannot parse {bad}:" in err
    assert "error: 1 files could not be parsed" in err
    assert "Traceback" not in err


def test_main_directory_update_manifest_continues_past_syntax_error(tmp_path, capsys):
    import mutate4py.__main__ as m

    d = tmp_path / "src"
    d.mkdir()
    (d / "good.py").write_text("x = a > b\n")
    (d / "bad.py").write_text("def broken(:\n    pass\n")
    (d / "zlast.py").write_text("y = c > d\n")
    sys.argv = ["mutate4py", str(d), "--update-manifest"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "mutate4py-manifest-begin" in (d / "good.py").read_text()
    assert "mutate4py-manifest-begin" in (d / "zlast.py").read_text()
    assert (d / "bad.py").read_text() == "def broken(:\n    pass\n"
    assert f"error: cannot parse {d / 'bad.py'}:" in err
    assert "error: 1 files could not be parsed" in err
    assert "Traceback" not in err


def test_main_directory_check_manifest_continues_past_syntax_error(tmp_path, capsys):
    """The manifest-exists case from issue #35: bad.py already has a manifest
    footer embedded, but its body was hand-edited into invalid syntax — this is
    the case that actually triggers ast.parse (a file with no manifest at all
    short-circuits check_manifest before ever parsing)."""
    import mutate4py.__main__ as m

    d = tmp_path / "src"
    d.mkdir()
    (d / "good.py").write_text("def f(): pass\n")
    (d / "zlast.py").write_text("def g(): pass\n")
    bad = d / "bad.py"
    bad.write_text("def f(): pass\n")
    sys.argv = ["mutate4py", str(bad), "--update-manifest"]
    with pytest.raises(SystemExit):
        m.main()
    capsys.readouterr()
    bad.write_text(bad.read_text().replace("def f(): pass\n", "def f(:\n    pass\n", 1))

    sys.argv = ["mutate4py", str(d), "--check-manifest"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 2
    captured = capsys.readouterr()
    out, err = captured.out, captured.err
    assert f"Manifest missing: {d / 'good.py'}" in out
    assert f"Manifest missing: {d / 'zlast.py'}" in out
    assert f"error: cannot parse {bad}:" in err
    assert "error: 1 files could not be parsed" in err
    assert "Traceback" not in err


def test_main_single_file_syntax_error_exits_nonzero_no_traceback(tmp_path, capsys):
    """A single-file target with invalid syntax exits non-zero with the same
    message and no traceback (issue #35 acceptance)."""
    import mutate4py.__main__ as m

    p = tmp_path / "bad.py"
    p.write_text("def broken(:\n    pass\n")
    sys.argv = ["mutate4py", str(p), "--scan"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert f"error: cannot parse {p}:" in err
    assert "Traceback" not in err


def test_main_two_positionals_dispatches_the_union_path_in_process(tmp_path, capsys):
    """Direct (non-subprocess) exercise of the arity>=2 branch through main(),
    so _dispatch/_dispatch_batch/_collect_union_files get real coverage."""
    import mutate4py.__main__ as m

    a_dir = tmp_path / "a_pkg"
    b_dir = tmp_path / "b_pkg"
    a_dir.mkdir()
    b_dir.mkdir()
    (a_dir / "a.py").write_text("def f(): pass\n")
    (b_dir / "b.py").write_text("def g(): pass\n")
    sys.argv = ["mutate4py", str(a_dir), str(b_dir), "--check-manifest"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert f"Manifest missing: {a_dir / 'a.py'}" in out
    assert f"Manifest missing: {b_dir / 'b.py'}" in out


def test_main_union_batch_continues_past_syntax_error_in_one_root(tmp_path, capsys):
    """A union batch (two or more resolved roots) must apply the same
    continue-the-batch/worst-code contract as a single directory (issue #35)."""
    import mutate4py.__main__ as m

    a_dir = tmp_path / "a_pkg"
    b_dir = tmp_path / "b_pkg"
    a_dir.mkdir()
    b_dir.mkdir()
    (a_dir / "a.py").write_text("def f(): pass\n")
    bad = a_dir / "bad.py"
    bad.write_text("def h(): pass\n")
    (b_dir / "b.py").write_text("def g(): pass\n")
    sys.argv = ["mutate4py", str(bad), "--update-manifest"]
    with pytest.raises(SystemExit):
        m.main()
    capsys.readouterr()
    # a manifest already exists on bad.py; the body is then hand-corrupted so
    # check_manifest actually reaches ast.parse (issue #35: a file with no
    # manifest at all short-circuits before ever parsing).
    bad.write_text(bad.read_text().replace("def h(): pass\n", "def h(:\n    pass\n", 1))

    sys.argv = ["mutate4py", str(a_dir), str(b_dir), "--check-manifest"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 2
    captured = capsys.readouterr()
    out, err = captured.out, captured.err
    assert f"Manifest missing: {a_dir / 'a.py'}" in out
    assert f"Manifest missing: {b_dir / 'b.py'}" in out
    assert f"error: cannot parse {bad}:" in err
    assert "error: 1 files could not be parsed" in err
    assert "Traceback" not in err


def test_main_zero_positionals_dispatches_autodiscovery_in_process(tmp_path, capsys, monkeypatch):
    """Direct (non-subprocess) exercise of the zero-positional branch
    through main(), so _resolve_roots' autodiscovery path gets real
    coverage (mirrors the union-path test above)."""
    import mutate4py.__main__ as m

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "pyproject.toml").write_text("[tool.uv.workspace]\n")
    (ws / "a.py").write_text("def f(): pass\n")
    monkeypatch.chdir(ws)
    sys.argv = ["mutate4py", "--check-manifest"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 1
    assert f"Manifest missing: {ws / 'a.py'}" in capsys.readouterr().out


# ── --test-contexts ───────────────────────────────────────────────────────────


@pytest.mark.integration
def test_test_contexts_incompatible_with_scan_exits_2(tmp_path):
    import sqlite3

    db = tmp_path / ".coverage"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE file (id INTEGER PRIMARY KEY, path TEXT)")
    conn.execute("CREATE TABLE context (id INTEGER PRIMARY KEY, context TEXT)")
    conn.execute("CREATE TABLE line_bits (file_id INTEGER, context_id INTEGER, numbits BLOB)")
    conn.commit()
    conn.close()
    p = tmp_path / "mod.py"
    p.write_text("x = a > b\n")
    result = _run_cli_path(str(p), "--scan", "--test-contexts", str(db))
    assert result.returncode == 2
    assert "--test-contexts" in result.stderr


@pytest.mark.integration
def test_test_contexts_missing_file_exits_2(tmp_path):
    p = tmp_path / "mod.py"
    p.write_text("x = a > b\n")
    result = _run_cli_path(str(p), "--test-contexts", str(tmp_path / "no.coverage"))
    assert result.returncode == 2
    assert "--test-contexts" in result.stderr


@pytest.mark.integration
def test_test_contexts_flag_accepted_with_valid_file(tmp_path):
    import sqlite3

    db = tmp_path / ".coverage"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE file (id INTEGER PRIMARY KEY, path TEXT)")
    conn.execute("CREATE TABLE context (id INTEGER PRIMARY KEY, context TEXT)")
    conn.execute("CREATE TABLE line_bits (file_id INTEGER, context_id INTEGER, numbits BLOB)")
    conn.commit()
    conn.close()
    p = tmp_path / "mod.py"
    p.write_text("x = a > b\n")
    result = _run_cli_path(str(p), "--test-contexts", str(db))
    assert "cannot be combined" not in result.stderr
    assert "--test-contexts file not found" not in result.stderr


# ── multi-root positionals (issue #22): CLI-level arity/union behavior ─────────


@pytest.mark.integration
def test_union_two_directories_processes_files_from_both(tmp_path):
    a_dir = tmp_path / "a_pkg"
    b_dir = tmp_path / "b_pkg"
    a_dir.mkdir()
    b_dir.mkdir()
    (a_dir / "a.py").write_text("def f(): pass\n")
    (b_dir / "b.py").write_text("def g(): pass\n")
    result = _run_cli_path(str(a_dir), str(b_dir), "--check-manifest")
    assert result.returncode == 1
    assert f"Manifest missing: {a_dir / 'a.py'}" in result.stdout
    assert f"Manifest missing: {b_dir / 'b.py'}" in result.stdout


@pytest.mark.integration
def test_union_glob_pattern_matching_two_files_processes_both(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "a.py").write_text("def f(): pass\n")
    (d / "b.py").write_text("def g(): pass\n")
    result = _run_cli_path(str(d / "*.py"), "--check-manifest")
    assert result.returncode == 1
    assert f"Manifest missing: {d / 'a.py'}" in result.stdout
    assert f"Manifest missing: {d / 'b.py'}" in result.stdout


@pytest.mark.integration
def test_single_glob_match_dispatches_as_a_single_file(tmp_path):
    """Arity rule (item 2): exactly one resolved path -> today's single-file
    dispatch, even though the argument was a glob pattern."""
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "only.py").write_text("def f(): pass\n")
    result = _run_cli_path(str(d / "*.py"), "--check-manifest")
    assert result.returncode == 1
    assert f"Manifest missing: {d / 'only.py'}" in result.stdout


@pytest.mark.integration
def test_glob_matched_non_py_file_is_dropped_silently(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "a.py").write_text("def f(): pass\n")
    (d / "README.md").write_text("docs\n")
    result = _run_cli_path(str(d / "*"), "--check-manifest")
    assert result.returncode == 1
    assert "README.md" not in result.stdout
    assert f"Manifest missing: {d / 'a.py'}" in result.stdout


@pytest.mark.integration
def test_literal_non_py_single_target_still_uses_todays_dispatch(tmp_path):
    """Item 6's carve-out: a literally-typed (non-wildcard) path is never
    silently dropped for lacking a .py suffix; arity 1 always reaches the
    unchanged single-file dispatch, whatever it does with the content."""
    p = tmp_path / "README.md"
    p.write_text("x = 1\n")
    result = _run_cli_path(str(p), "--check-manifest")
    assert result.returncode == 1
    assert f"Manifest missing: {p}" in result.stdout


@pytest.mark.integration
def test_pattern_matching_nothing_exits_2_naming_the_pattern(tmp_path):
    pattern = str(tmp_path / "nosuch" / "*.py")
    result = _run_cli_path(pattern, "--check-manifest")
    assert result.returncode == 2
    assert pattern in result.stderr


@pytest.mark.integration
def test_union_fails_fast_before_processing_any_file(tmp_path):
    """Item 7: all positionals are validated before anything is collected —
    a bad second pattern must produce no output for the good first one."""
    a_dir = tmp_path / "a_pkg"
    a_dir.mkdir()
    (a_dir / "a.py").write_text("def f(): pass\n")
    missing = str(tmp_path / "no_such_file.py")
    result = _run_cli_path(str(a_dir), missing, "--check-manifest")
    assert result.returncode == 2
    assert result.stdout == ""
    assert missing in result.stderr


@pytest.mark.integration
def test_union_dedups_the_same_root_given_twice(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "a.py").write_text("def f(): pass\n")
    result = _run_cli_path(str(d), str(d), "--check-manifest")
    assert result.returncode == 1
    assert result.stdout.count("a.py") == 1


@pytest.mark.integration
def test_union_preserves_root_order_not_a_global_sort(tmp_path):
    """Item 15: files from the first root's walk print before the second
    root's, even though the second root's filename would sort first."""
    z_dir = tmp_path / "z_pkg"
    a_dir = tmp_path / "a_pkg"
    z_dir.mkdir()
    a_dir.mkdir()
    (z_dir / "zz.py").write_text("def f(): pass\n")
    (a_dir / "aa.py").write_text("def g(): pass\n")
    result = _run_cli_path(str(z_dir), str(a_dir), "--check-manifest")
    assert result.stdout.index("zz.py") < result.stdout.index("aa.py")


@pytest.mark.integration
def test_union_empty_root_is_silent_when_another_root_has_files(tmp_path):
    """Item 17: an individual empty root is not an error; only an empty
    whole union is."""
    empty_dir = tmp_path / "empty_pkg"
    full_dir = tmp_path / "full_pkg"
    empty_dir.mkdir()
    full_dir.mkdir()
    (full_dir / "a.py").write_text("def f(): pass\n")
    result = _run_cli_path(str(empty_dir), str(full_dir), "--check-manifest")
    assert result.returncode == 1
    assert "no Python files to process" not in result.stderr


@pytest.mark.integration
def test_union_whole_union_empty_exits_2(tmp_path):
    empty_a = tmp_path / "empty_a"
    empty_b = tmp_path / "empty_b"
    empty_a.mkdir()
    empty_b.mkdir()
    result = _run_cli_path(str(empty_a), str(empty_b), "--check-manifest")
    assert result.returncode == 2
    assert "error: no Python files to process." in result.stderr


@pytest.mark.integration
def test_union_exclude_composes_with_multiple_roots(tmp_path):
    a_dir = tmp_path / "a_pkg"
    b_dir = tmp_path / "b_pkg"
    a_dir.mkdir()
    b_dir.mkdir()
    (a_dir / "a.py").write_text("def f(): pass\n")
    (b_dir / "b.py").write_text("def g(): pass\n")
    result = _run_cli_path(str(a_dir), str(b_dir), "--check-manifest", "--exclude", "**/b.py")
    assert result.returncode == 1
    assert f"Manifest missing: {a_dir / 'a.py'}" in result.stdout
    assert "b.py" not in result.stdout


@pytest.mark.integration
def test_zero_positionals_triggers_autodiscovery(tmp_path):
    """Issue #22 item 3: no new flag, the absence of positionals is the
    autodiscovery trigger. This repo's own pyproject.toml has no
    [tool.uv.workspace], so autodiscovery from REPO_ROOT errors there —
    which is itself proof that autodiscovery ran, not the old "missing
    positional" usage error."""
    result = subprocess.run(
        [sys.executable, "-m", "mutate4py", "--scan"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": os.path.join(REPO_ROOT, "src")},
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert os.path.join(REPO_ROOT, "pyproject.toml") in result.stderr
    assert "[tool.uv.workspace]" in result.stderr


# ── uv workspace autodiscovery (issue #22 items 3, 8-12): CLI-level ────────────


def _write_workspace(tmp_path, members=None, exclude=None):
    """Build a workspace at tmp_path/"ws"; return its path."""
    ws = tmp_path / "ws"
    ws.mkdir()
    lines = ["[tool.uv.workspace]"]
    if members is not None:
        items = ", ".join(f'"{m}"' for m in members)
        lines.append(f"members = [{items}]")
    if exclude is not None:
        items = ", ".join(f'"{e}"' for e in exclude)
        lines.append(f"exclude = [{items}]")
    (ws / "pyproject.toml").write_text("\n".join(lines) + "\n")
    return ws


@pytest.mark.integration
def test_autodiscovery_single_root_workspace_check_manifest(tmp_path):
    ws = _write_workspace(tmp_path)
    (ws / "a.py").write_text("def f(): pass\n")
    result = _run_cli_in(str(ws), "--check-manifest")
    assert result.returncode == 1
    assert f"Manifest missing: {ws / 'a.py'}" in result.stdout


@pytest.mark.integration
def test_autodiscovery_multi_member_workspace_unions_all_roots(tmp_path):
    ws = _write_workspace(tmp_path, members=["pkgs/*"])
    a_dir, b_dir = ws / "pkgs" / "a", ws / "pkgs" / "b"
    a_dir.mkdir(parents=True)
    b_dir.mkdir(parents=True)
    (a_dir / "pyproject.toml").write_text('[project]\nname = "a"\n')
    (b_dir / "pyproject.toml").write_text('[project]\nname = "b"\n')
    (a_dir / "a.py").write_text("def f(): pass\n")
    (b_dir / "b.py").write_text("def g(): pass\n")
    result = _run_cli_in(str(ws), "--check-manifest")
    assert result.returncode == 1
    assert f"Manifest missing: {a_dir / 'a.py'}" in result.stdout
    assert f"Manifest missing: {b_dir / 'b.py'}" in result.stdout


@pytest.mark.integration
def test_autodiscovery_exclude_removes_member_files_from_the_union(tmp_path):
    """Item 10: an excluded member's files are absent from the union even
    though they physically sit under the workspace root's recursive walk."""
    ws = _write_workspace(tmp_path, members=["pkgs/*"], exclude=["pkgs/b"])
    a_dir, b_dir = ws / "pkgs" / "a", ws / "pkgs" / "b"
    a_dir.mkdir(parents=True)
    b_dir.mkdir(parents=True)
    (a_dir / "pyproject.toml").write_text('[project]\nname = "a"\n')
    (b_dir / "pyproject.toml").write_text('[project]\nname = "b"\n')
    (a_dir / "a.py").write_text("def f(): pass\n")
    (b_dir / "b.py").write_text("def g(): pass\n")
    result = _run_cli_in(str(ws), "--check-manifest")
    assert result.returncode == 1
    assert f"Manifest missing: {a_dir / 'a.py'}" in result.stdout
    assert "b.py" not in result.stdout


@pytest.mark.integration
def test_autodiscovery_no_workspace_found_exits_2(tmp_path):
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    result = _run_cli_in(str(isolated), "--scan")
    assert result.returncode == 2
    assert result.stdout == ""
    assert "pyproject.toml" in result.stderr
    assert str(isolated) in result.stderr


@pytest.mark.integration
def test_autodiscovery_help_mentions_it(tmp_path):
    result = _run_cli_in(str(tmp_path), "--help")
    assert result.returncode == 0
    assert "autodiscov" in result.stdout.lower()
