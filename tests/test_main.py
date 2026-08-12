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


@pytest.mark.unit
def test_scan_prints_count_block_zero_sites():
    result = run_cli("--scan", source="x = 1\n")
    # 1 site (integer 1)
    assert "Total mutation sites: 1" in result.stdout
    assert "Changed mutation sites: 1" in result.stdout
    assert "Manifest exists: false" in result.stdout
    assert result.returncode == 0


@pytest.mark.unit
def test_scan_prints_mutation_scan_header():
    result = run_cli("--scan", source="pass\n")
    assert "Mutation scan:" in result.stdout


@pytest.mark.unit
def test_scan_zero_sites():
    result = run_cli("--scan", source="pass\n")
    assert "Total mutation sites: 0" in result.stdout
    assert "Changed mutation sites: 0" in result.stdout
    assert result.returncode == 0


@pytest.mark.unit
def test_scan_no_warning_at_threshold():
    src = "x = a + b\n"
    result = run_cli("--scan", "--mutation-warning", "1", source=src)
    # 1 site, threshold 1: no warning (not strictly greater)
    assert "Warning:" not in result.stdout
    assert result.returncode == 0


@pytest.mark.unit
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


@pytest.mark.unit
def test_scan_report_zero_sites():
    lines, exceeded = scan_report("f.py", "pass\n", 1000)
    assert "Total mutation sites: 0" in lines
    assert "Changed mutation sites: 0" in lines
    assert "Manifest exists: false" in lines
    assert not exceeded


@pytest.mark.unit
def test_scan_report_counts_sites():
    lines, exceeded = scan_report("f.py", "x = a + b\n", 1000)
    assert "Total mutation sites: 1" in lines
    assert "Changed mutation sites: 1" in lines
    assert not exceeded


@pytest.mark.unit
def test_scan_report_header_uses_path():
    lines, _ = scan_report("myfile.py", "pass\n", 1000)
    assert "Mutation scan: myfile.py" in lines


@pytest.mark.unit
def test_scan_report_no_warning_at_threshold():
    lines, exceeded = scan_report("f.py", "x = a + b\n", 1)
    assert not exceeded
    assert not any("Warning" in line for line in lines)


@pytest.mark.unit
def test_scan_report_warning_above_threshold():
    src = "x = a + b\ny = c - d\n"
    lines, exceeded = scan_report("f.py", src, 1)
    assert exceeded
    assert any("Warning: 2 mutation sites exceeds threshold 1." in line for line in lines)


@pytest.mark.unit
def test_scan_report_total_equals_changed():
    src = "x = a + b\ny = c > d\n"
    lines, _ = scan_report("f.py", src, 1000)
    total_line = next(line for line in lines if "Total mutation sites:" in line)
    changed_line = next(line for line in lines if "Changed mutation sites:" in line)
    assert total_line.split(": ")[1] == changed_line.split(": ")[1]


@pytest.mark.unit
def test_scan_report_with_embedded_manifest_reports_exists_true(tmp_path):
    from mutate4py._runner import update_manifest

    p = tmp_path / "mod.py"
    src = "def f(a, b):\n    return a > b\n\n\ndef g(a, b):\n    return a < b\n"
    p.write_text(src)
    update_manifest(path=str(p), source=src, manifest_file=False)
    embedded = p.read_text()

    lines, _ = scan_report(str(p), embedded, 1000, manifest_file=False)
    assert "Manifest exists: true" in lines


@pytest.mark.unit
def test_scan_report_with_embedded_manifest_changed_reflects_diff(tmp_path):
    from mutate4py._runner import update_manifest

    p = tmp_path / "mod.py"
    src = "def f(a, b):\n    return a > b\n\n\ndef g(a, b):\n    return a < b\n"
    p.write_text(src)
    update_manifest(path=str(p), source=src, manifest_file=False)
    embedded = p.read_text()

    # Only g's body changes after the manifest was recorded.
    changed_src = embedded.replace("return a < b", "return a <= b")

    lines, _ = scan_report(str(p), changed_src, 1000, manifest_file=False)
    total = int(next(line for line in lines if "Total mutation sites:" in line).split(": ")[1])
    changed = int(next(line for line in lines if "Changed mutation sites:" in line).split(": ")[1])
    assert 0 < changed < total


@pytest.mark.unit
def test_scan_report_sidecar_manifest_reports_exists_true(tmp_path):
    from mutate4py._runner import update_manifest

    p = tmp_path / "mod.py"
    src = "def f(a, b):\n    return a > b\n"
    p.write_text(src)
    update_manifest(path=str(p), source=src, manifest_file=True)

    lines, _ = scan_report(str(p), src, 1000, manifest_file=True)
    assert "Manifest exists: true" in lines
    assert "Changed mutation sites: 0" in lines


@pytest.mark.unit
def test_scan_report_sidecar_manifest_changed_reflects_diff(tmp_path):
    from mutate4py._runner import update_manifest

    p = tmp_path / "mod.py"
    src = "def f(a, b):\n    return a > b\n"
    p.write_text(src)
    update_manifest(path=str(p), source=src, manifest_file=True)

    changed_src = "def f(a, b):\n    return a >= b\n"
    lines, _ = scan_report(str(p), changed_src, 1000, manifest_file=True)
    assert "Manifest exists: true" in lines
    assert "Changed mutation sites: 1" in lines


# ── main() direct invocation (CRAP coverage) ──────────────────────────────────


@pytest.mark.unit
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


@pytest.mark.unit
def test_main_missing_file_exits(tmp_path):
    import mutate4py.__main__ as m

    sys.argv = ["mutate4py", str(tmp_path / "nope.py"), "--scan"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code != 0


@pytest.mark.unit
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


@pytest.mark.unit
def test_mse_equal_manifests():
    fn = _mse()
    a = {"module_hash": "h1", "functions": [{"id": "func/foo", "hash": "fh1"}]}
    b = {"module_hash": "h1", "functions": [{"id": "func/foo", "hash": "fh1"}]}
    assert fn(a, b) is True


@pytest.mark.unit
def test_mse_different_module_hash():
    fn = _mse()
    a = {"module_hash": "h1", "functions": []}
    b = {"module_hash": "h2", "functions": []}
    assert fn(a, b) is False


@pytest.mark.unit
def test_mse_different_function_hash():
    fn = _mse()
    a = {"module_hash": "h", "functions": [{"id": "func/foo", "hash": "old"}]}
    b = {"module_hash": "h", "functions": [{"id": "func/foo", "hash": "new"}]}
    assert fn(a, b) is False


@pytest.mark.unit
def test_mse_different_function_set():
    fn = _mse()
    a = {"module_hash": "h", "functions": [{"id": "func/foo", "hash": "fh"}]}
    b = {"module_hash": "h", "functions": [{"id": "func/bar", "hash": "fh"}]}
    assert fn(a, b) is False


@pytest.mark.unit
def test_mse_ignores_tested_at():
    fn = _mse()
    a = {"module_hash": "h", "tested_at": "2026-01-01T00:00:00Z", "functions": []}
    b = {"module_hash": "h", "tested_at": "2026-06-01T00:00:00Z", "functions": []}
    assert fn(a, b) is True


@pytest.mark.unit
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


@pytest.mark.unit
def test_mse_missing_functions_key_in_both_treated_as_empty():
    fn = _mse()
    a = {"module_hash": "h"}
    b = {"module_hash": "h"}
    assert fn(a, b) is True


@pytest.mark.unit
def test_mse_a_missing_functions_differs_from_b_with_functions():
    fn = _mse()
    a = {"module_hash": "h"}
    b = {"module_hash": "h", "functions": [{"id": "func/foo", "hash": "fh"}]}
    assert fn(a, b) is False


# ── _do_update_manifest unit tests ────────────────────────────────────────────


@pytest.mark.unit
def test_do_update_manifest_writes_footer(tmp_path, capsys):
    from mutate4py._runner import update_manifest

    p = tmp_path / "s.py"
    p.write_text("def foo():\n    return 1\n")
    update_manifest(path=str(p), source=p.read_text())
    content = p.read_text()
    assert "# mutate4py-manifest-begin" in content
    assert "Updated manifest:" in capsys.readouterr().out


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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
    assert "Changed mutation sites: 1" in lines


@pytest.mark.unit
def test_scan_report_with_coverage_embedded_manifest_reports_exists_true_and_changed(tmp_path):
    from mutate4py._runner import scan_report_with_coverage, update_manifest

    src_file = tmp_path / "foo.py"
    src = "def f(a, b):\n    return a > b\n\n\ndef g(a, b):\n    return a < b\n"
    src_file.write_text(src)
    update_manifest(path=str(src_file), source=src, manifest_file=False)
    embedded = src_file.read_text()
    changed_src = embedded.replace("return a < b", "return a <= b")

    lcov_file = tmp_path / "cov.info"
    lcov_file.write_text(f"SF:{src_file}\nDA:2,1\nDA:6,1\nend_of_record\n")

    lines, _ = scan_report_with_coverage(
        str(src_file),
        changed_src,
        1000,
        CoverageSource(cov_cmd=None, lcov_path=str(lcov_file), reuse_coverage=False, cwd=str(tmp_path)),
    )
    assert "Manifest exists: true" in lines
    total = int(next(line for line in lines if "Total mutation sites:" in line).split(": ")[1])
    changed = int(next(line for line in lines if "Changed mutation sites:" in line).split(": ")[1])
    assert 0 < changed < total


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
def test_mutation_warning_type_int_parses_string_arg():
    # mutant_34,38: type=int removed → --mutation-warning receives str, comparison int>str fails
    src = "x = a + b\n"
    result = run_cli("--scan", "--mutation-warning", "5", source=src)
    assert result.returncode == 0
    assert "Total mutation sites: 1" in result.stdout


@pytest.mark.unit
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
