"""Run-level component tests for how the Measurement's Baseline and per-Mutant
overhead surface in a run's Mutation Report (issue 06), and for a run whose
Measurement fails. The Measurement's own indexing and exit-status rules are
pinned in test_measurement_index.py; the no-flag Coverage gate in
test_measurement_gate.py."""

import logging
import os
import re

import pytest

from ._measurement_helpers import measurement_for
from ._pytest_project_helpers import (
    write_always_failing_pytest_project,
    write_always_passing_pytest_project,
)
from mutate4py._discovery import discover_sites
from mutate4py._runner import RunMutationsRequest, run_mutations

SRC = "def f(a, b):\n    return a > b\n"


def _write_lcov(path: str, source_abs: str, covered_lines: list[int]) -> None:
    da_lines = "\n".join(f"DA:{ln},1" for ln in covered_lines)
    content = f"SF:{source_abs}\n{da_lines}\nend_of_record\n"
    with open(path, "w") as f:
        f.write(content)


def _write_source_and_lcov(tmp_path) -> tuple[str, str]:
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(SRC)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov(lcov_path, src_path, [s.line for s in discover_sites(SRC)])
    return src_path, lcov_path


def _flagged_request(tmp_path, src_path, lcov_path, pytest_args, measurement=None) -> RunMutationsRequest:
    return RunMutationsRequest(
        path=src_path,
        source=SRC,
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
        measurement=measurement,
    )


@pytest.mark.component
def test_run_mutations_reports_per_mutant_overhead(tmp_path, caplog):
    """A run given no injected Measurement runs one itself, and its Mutation
    Report carries the fixed per-Mutant overhead the Measurement measured:
    presence and shape only, never the measured value, which is
    machine-dependent (issue 06)."""
    caplog.set_level(logging.INFO)
    src_path, lcov_path = _write_source_and_lcov(tmp_path)
    pytest_args = write_always_passing_pytest_project(str(tmp_path))

    rc = run_mutations(_flagged_request(tmp_path, src_path, lcov_path, pytest_args))

    assert rc == 3
    output = "\n".join(caplog.messages)
    match = re.search(r"^Per-Mutant overhead: (\d+\.\d\ds)$", output, re.MULTILINE)
    assert match, f"no 'Per-Mutant overhead:' line found in:\n{output}"


@pytest.mark.component
def test_run_mutations_omits_overhead_when_the_measurement_is_injected(tmp_path, caplog):
    """An injected Measurement was taken by the caller, who owns the overhead
    line; the run must not claim an overhead it did not measure."""
    caplog.set_level(logging.INFO)
    src_path, lcov_path = _write_source_and_lcov(tmp_path)
    pytest_args = write_always_passing_pytest_project(str(tmp_path))
    measurement = measurement_for(os.path.abspath(src_path), {}, wall=0.01)

    rc = run_mutations(_flagged_request(tmp_path, src_path, lcov_path, pytest_args, measurement))

    assert rc == 3
    assert "Per-Mutant overhead:" not in caplog.text


@pytest.mark.component
def test_run_mutations_measurement_failure_exits_1(tmp_path, caplog):
    """A suite that fails under the Measurement gives the run no Baseline, so
    it stops before any Mutant and names the Measurement as the cause."""
    caplog.set_level(logging.INFO)
    src_path, lcov_path = _write_source_and_lcov(tmp_path)
    pytest_args = write_always_failing_pytest_project(str(tmp_path))

    rc = run_mutations(_flagged_request(tmp_path, src_path, lcov_path, pytest_args))

    assert rc == 1
    assert "baseline failed: " in caplog.text
    assert "tests/test_always_fails.py::test_fail" in caplog.text
    assert "Mutation Report" not in caplog.text
    # No backup left
    assert not os.path.exists(src_path + ".bak")
