"""Unit tests for baseline timing and per-Mutant overhead (_baseline.py),
plus the run_mutations-level integration tests that pin how those
measurements surface in the Mutation Report (issue 06)."""

import os

from ._pytest_project_helpers import (
    write_always_failing_pytest_project,
    write_always_passing_pytest_project,
)
from mutate4py._baseline import _baseline_reason
from mutate4py._discovery import discover_sites
from mutate4py._runner import RunMutationsRequest, run_mutations
import pytest


# ── _baseline_reason ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_baseline_reason_uses_stderr_first():
    import subprocess

    result = subprocess.CompletedProcess(args=[], returncode=1, stderr=b"test suite crashed\nsecond line")
    assert _baseline_reason(result) == "test suite crashed"


@pytest.mark.unit
def test_baseline_reason_falls_back_to_exit_code():
    import subprocess

    result = subprocess.CompletedProcess(args=[], returncode=42, stderr=b"")
    assert _baseline_reason(result) == "exit code 42"


# ── run_mutations integration: baseline/overhead reporting ────────────────────


def _write_lcov(path: str, source_abs: str, covered_lines: list[int]) -> None:
    da_lines = "\n".join(f"DA:{ln},1" for ln in covered_lines)
    content = f"SF:{source_abs}\n{da_lines}\nend_of_record\n"
    with open(path, "w") as f:
        f.write(content)


@pytest.mark.component
def test_run_mutations_reports_per_mutant_overhead(tmp_path):
    """A real run (no pre-supplied baseline_duration) measures the fixed
    per-Mutant overhead via the extra collect-only pass and prints it in the
    Mutation Report — presence and shape only, never the measured value,
    which is machine-dependent (issue 06)."""
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    sites = discover_sites(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov(lcov_path, src_path, [s.line for s in sites])

    pytest_args = write_always_passing_pytest_project(str(tmp_path))

    import io
    import re
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                cov_cmd=None,
                lcov_path=lcov_path,
                reuse_coverage=False,
                pytest_args=pytest_args,
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                cwd=str(tmp_path),
            )
        )
    output = buf.getvalue()
    assert rc == 0
    match = re.search(r"^Per-Mutant overhead: (\d+\.\d\ds)$", output, re.MULTILINE)
    assert match, f"no 'Per-Mutant overhead:' line found in:\n{output}"


@pytest.mark.component
def test_run_mutations_omits_overhead_when_baseline_duration_is_pre_supplied(tmp_path):
    """A pre-supplied baseline_duration means no fresh Baseline ran, so there
    is nothing to attach the extra collect-only pass to — the report must not
    claim a measurement that never happened."""
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    sites = discover_sites(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov(lcov_path, src_path, [s.line for s in sites])

    pytest_args = write_always_passing_pytest_project(str(tmp_path))

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                cov_cmd=None,
                lcov_path=lcov_path,
                reuse_coverage=False,
                pytest_args=pytest_args,
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                cwd=str(tmp_path),
                baseline_duration=0.01,
            )
        )
    output = buf.getvalue()
    assert rc == 0
    assert "Per-Mutant overhead:" not in output


@pytest.mark.component
def test_run_mutations_baseline_failure_exits_1(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    sites = discover_sites(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov(lcov_path, src_path, [s.line for s in sites])

    pytest_args = write_always_failing_pytest_project(str(tmp_path))

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                cov_cmd=None,
                lcov_path=lcov_path,
                reuse_coverage=False,
                pytest_args=pytest_args,
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                cwd=str(tmp_path),
            )
        )
    output = buf.getvalue()
    assert rc == 1
    assert "baseline failed:" in output
    assert "Mutation Report" not in output
    # No backup left
    assert not os.path.exists(src_path + ".bak")
