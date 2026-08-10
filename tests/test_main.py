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


def test_build_parser_pytest_args_defaults_none():
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py"])
    assert args.pytest_args is None


def test_build_parser_pytest_args_sets_raw_string():
    """--pytest-args is stored raw here; _dispatch tokenizes it (see test_dispatch.py)."""
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py", "--pytest-args", "-x -k foo"])
    assert args.pytest_args == "-x -k foo"


def test_build_parser_rejects_test_command():
    """--test-command no longer exists; passing it is a usage error."""
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["f.py", "--test-command", "pytest"])
    assert exc.value.code == 2


def test_build_parser_no_fork_defaults_false():
    """The forking executor fast path is on by default: --no-fork absent -> False."""
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py"])
    assert args.no_fork is False


def test_build_parser_no_fork_flag_sets_true():
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py", "--no-fork"])
    assert args.no_fork is True


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
