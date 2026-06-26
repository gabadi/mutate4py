"""Unit tests for acceptance/steps/coverage_helpers.py."""
import os
import tempfile

from acceptance.steps.coverage_helpers import (
    assert_cmd_ran_n_times,
    make_calc_source,
    make_lcov,
    make_source_with_sites_on_lines,
    resolve_sf_path,
    substitute_cmd_placeholders,
    substitute_qa_cmd_placeholders,
    write_counter_script,
)


# ── make_source_with_sites_on_lines ──────────────────────────────────────────

def test_make_source_sites_on_given_lines():
    src = make_source_with_sites_on_lines("3,5")
    lines = src.splitlines()
    assert lines[2] == "x = a + b"
    assert lines[4] == "x = a + b"
    assert lines[0] == ""
    assert lines[1] == ""


def test_make_source_empty_string():
    src = make_source_with_sites_on_lines("")
    assert src == "\n"


def test_make_source_single_line():
    src = make_source_with_sites_on_lines("1")
    assert src.splitlines()[0] == "x = a + b"


# ── make_calc_source ─────────────────────────────────────────────────────────

def test_make_calc_source_puts_compare_expr():
    src = make_calc_source("2,4")
    lines = src.splitlines()
    assert lines[1] == "x = a > b"
    assert lines[3] == "x = a > b"
    assert lines[0] == ""
    assert lines[2] == ""


# ── make_lcov ────────────────────────────────────────────────────────────────

def test_make_lcov_format():
    text = make_lcov("/src/foo.py", {3, 5})
    assert "SF:/src/foo.py" in text
    assert "DA:3,1" in text
    assert "DA:5,1" in text
    assert "end_of_record" in text


def test_make_lcov_empty_lines():
    text = make_lcov("/src/foo.py", set())
    assert "SF:/src/foo.py" in text
    assert "DA:" not in text


# ── resolve_sf_path ──────────────────────────────────────────────────────────

def test_resolve_sf_absolute_suffix():
    result = resolve_sf_path("absolute-suffix", "/abs/path/foo.py")
    assert result == "/abs/path/foo.py"


def test_resolve_sf_relative_suffix():
    result = resolve_sf_path("relative-suffix", "/abs/path/foo.py")
    assert result == "foo.py"


def test_resolve_sf_passthrough():
    result = resolve_sf_path("/other/path.py", "/abs/path/foo.py")
    assert result == "/other/path.py"


# ── write_counter_script ─────────────────────────────────────────────────────

def test_write_counter_script_creates_executable():
    with tempfile.TemporaryDirectory() as d:
        script = os.path.join(d, "run.sh")
        counter = os.path.join(d, "count.log")
        lcov = os.path.join(d, "cov.lcov")
        write_counter_script(script, counter, lcov, "SF:foo\nend_of_record\n")
        assert os.access(script, os.X_OK)


# ── assert_cmd_ran_n_times ───────────────────────────────────────────────────

def test_assert_cmd_ran_zero_no_file():
    with tempfile.TemporaryDirectory() as d:
        assert_cmd_ran_n_times(d, 0)  # no file → passes


def test_assert_cmd_ran_zero_fails_if_file_exists():
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "cov_runs.log"), "w").close()
        try:
            assert_cmd_ran_n_times(d, 0)
            assert False, "expected AssertionError"
        except AssertionError:
            pass


def test_assert_cmd_ran_once():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "cov_runs.log"), "w") as f:
            f.write("x")
        assert_cmd_ran_n_times(d, 1)


def test_assert_cmd_ran_mismatch_fails():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "cov_runs.log"), "w") as f:
            f.write("xx")
        try:
            assert_cmd_ran_n_times(d, 1)
            assert False, "expected AssertionError"
        except AssertionError:
            pass


# ── substitute_cmd_placeholders ───────────────────────────────────────────────

def test_substitute_cmd_cmd_token():
    result = substitute_cmd_placeholders("--cov-cmd CMD", "/tmp/d", "/scripts/run.sh")
    assert result == "--cov-cmd /scripts/run.sh"


def test_substitute_cmd_lcov_token():
    result = substitute_cmd_placeholders("--lcov cov.info", "/tmp/d", None)
    assert result == f"--lcov {os.path.join('/tmp/d', 'cov.info')}"


def test_substitute_cmd_no_change():
    result = substitute_cmd_placeholders("--scan", "/tmp/d", None)
    assert result == "--scan"


# ── substitute_qa_cmd_placeholders ────────────────────────────────────────────

def test_substitute_qa_cmd_token():
    result = substitute_qa_cmd_placeholders("--cov-cmd CMD", "/tmp/d", "/run.sh", None)
    assert "--cov-cmd /run.sh" in result


def test_substitute_qa_that_command_token():
    result = substitute_qa_cmd_placeholders("--cov-cmd '<that command>'", "/tmp/d", "/run.sh", None)
    assert "--cov-cmd /run.sh" in result


def test_substitute_qa_abspath_calc():
    result = substitute_qa_cmd_placeholders("<abspath>/calc.py --scan", "/tmp/d", None, "/abs/calc.py")
    assert result.startswith("/abs/calc.py")


def test_substitute_qa_bare_calc():
    result = substitute_qa_cmd_placeholders("calc.py --scan", "/tmp/d", None, "/abs/calc.py")
    assert result.startswith("/abs/calc.py")


def test_substitute_qa_lcov_path():
    result = substitute_qa_cmd_placeholders("calc.py --lcov cov.info", "/tmp/d", None, "/abs/calc.py")
    assert f"--lcov {os.path.join('/tmp/d', 'cov.info')}" in result


# ── assert_stdout_contains / assert_stdout_not_contains ──────────────────────

class _FakeResult:
    def __init__(self, stdout, stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


from acceptance.steps.coverage_helpers import (  # noqa: E402
    assert_baseline_scan,
    assert_exit_nonzero,
    assert_exit_zero,
    assert_stdout_contains,
    assert_stdout_not_contains,
    make_lcov_brda_only,
    make_lcov_da_zero,
    make_lcov_single_da,
    make_noop_script,
    step_param,
)


def test_assert_stdout_contains_passes():
    assert_stdout_contains(_FakeResult("Total mutation sites: 5"), "Total mutation sites: 5")


def test_assert_stdout_contains_fails():
    try:
        assert_stdout_contains(_FakeResult("something else"), "Total mutation sites: 5")
        assert False
    except AssertionError:
        pass


def test_assert_stdout_not_contains_passes():
    assert_stdout_not_contains(_FakeResult("unrelated"), "Covered mutation sites:")


def test_assert_stdout_not_contains_fails():
    try:
        assert_stdout_not_contains(_FakeResult("Covered mutation sites: 3"), "Covered mutation sites:")
        assert False
    except AssertionError:
        pass


def test_assert_exit_zero_passes():
    assert_exit_zero(_FakeResult("ok", returncode=0))


def test_assert_exit_zero_fails():
    try:
        assert_exit_zero(_FakeResult("", returncode=1))
        assert False
    except AssertionError:
        pass


def test_assert_exit_nonzero_passes():
    assert_exit_nonzero(_FakeResult("", returncode=1))


def test_assert_exit_nonzero_fails():
    try:
        assert_exit_nonzero(_FakeResult("", returncode=0))
        assert False
    except AssertionError:
        pass


def test_assert_baseline_scan_passes():
    assert_baseline_scan(_FakeResult("Total mutation sites: 3"), 3)


def test_assert_baseline_scan_fails_wrong_count():
    try:
        assert_baseline_scan(_FakeResult("Total mutation sites: 5"), 3)
        assert False
    except AssertionError:
        pass


def test_make_lcov_da_zero():
    text = make_lcov_da_zero("/src/foo.py", 7)
    assert "DA:7,0" in text
    assert "SF:/src/foo.py" in text


def test_make_lcov_brda_only():
    text = make_lcov_brda_only("/src/foo.py", 3)
    assert "BRDA:3,0,0,1" in text
    assert "\nDA:" not in text


def test_make_lcov_single_da():
    text = make_lcov_single_da("foo.py", 5)
    assert "DA:5,1" in text
    assert "SF:foo.py" in text


def test_make_noop_script_runs():
    import subprocess
    with tempfile.TemporaryDirectory() as d:
        script = make_noop_script(os.path.join(d, "noop.sh"))
        result = subprocess.run([script], capture_output=True)
        assert result.returncode == 0


def test_step_param_uses_params_when_present():
    class FakeM:
        def group(self, n):
            return "from_match"
    assert step_param(FakeM(), {"key": "from_params"}, "key") == "from_params"


def test_step_param_falls_back_to_match():
    class FakeM:
        def group(self, n):
            return "from_match"
    assert step_param(FakeM(), {}, "key") == "from_match"
