"""The Measurement is the Coverage gate on a run given no coverage flag.

A run with none of --cov-cmd, --lcov or --reuse-coverage takes its covered
lines from the Measurement, Empty context included, instead of from a coverage
file. The tests that inject a Measurement build it from in-memory coverage data
(see `_measurement_helpers`); the tests that measure for real run pytest on a
small project under the run's cwd. Report text is asserted through caplog,
because the run's report blocks go through logging.
"""

import argparse
import io
import logging
import os
from contextlib import redirect_stdout

import pytest
from coverage import CoverageData

from ._measurement_helpers import measurement_for, record_for
from ._pytest_project_helpers import write_always_failing_pytest_project
from mutate4py._dispatch import _run_files_and_exit
from mutate4py._executor import ExecutorDescription
from mutate4py._measurement import measurement_from
from mutate4py._runner import RunMutationsRequest, run_mutations
from mutate4py._test_dispatch import NO_TESTS_HINT

# One mutation site, on line 2.
SRC = "def f(a, b):\n    return a > b\n"

# Records every test node id the session starts, once each, to the file named by
# $MUTATE4PY_FIXTURE_RAN, so a test can count how many sessions ran the suite.
FIXTURE_CONFTEST = """\
import os


def pytest_runtest_logstart(nodeid, location):
    with open(os.environ["MUTATE4PY_FIXTURE_RAN"], "a") as f:
        f.write(nodeid + "\\n")
"""


class _FakeExecutor:
    """Stands in for the forking and subprocess executors: records every
    Mutant dispatched and reports each one killed."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.primed = False

    def prime(self) -> None:
        self.primed = True

    def run(self, args, timeout):
        self.calls.append(list(args))
        return "killed"

    def describe(self) -> ExecutorDescription:
        return ExecutorDescription(mode="subprocess", reason="--no-fork")


def _write_source(tmp_path) -> str:
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(SRC)
    return src_path


def _measured_test(tmp_path, src_path: str):
    """A Measurement in which one test reached line 2. The test file is on disk, as a collected file
    is: the run's digest of the function reads it (#105)."""
    test_file = tmp_path / "tests" / "test_calc.py"
    test_file.parent.mkdir(exist_ok=True)
    test_file.write_text("def test_gt():\n    assert True\n")
    return measurement_for(os.path.abspath(src_path), {"tests/test_calc.py::test_gt": [2]}, wall=0.5)


def _run_without_coverage_flags(
    tmp_path, src_path, measurement, executor, pytest_args=(), **request_fields
) -> tuple[int, str]:
    request = RunMutationsRequest(
        path=src_path,
        source=SRC,
        pytest_args=list(pytest_args),
        timeout_factor=10,
        mutate_all=False,
        warning_threshold=1000,
        cwd=str(tmp_path),
        executor=executor,
        measurement=measurement,
        **request_fields,
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_mutations(request)
    return rc, buf.getvalue()


def _batch_args(**overrides) -> argparse.Namespace:
    """The argparse namespace a directory run reads, with no coverage flag and no run mode."""
    defaults = dict(
        scan=False,
        update_manifest=False,
        check_manifest=False,
        mutate_all=False,
        max_workers=None,
        timeout_factor=10,
        min_timeout=1.0,
        pytest_args=[],
        warning_threshold=1000,
        manifest_file=False,
        verbose=False,
        exclude=None,
        prune_dirs=(),
        no_fork=False,
        allow_survivors=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


@pytest.mark.component
def test_a_line_reached_only_at_import_time_is_covered_and_mutated_on_a_no_flag_run(tmp_path):
    src_path = _write_source(tmp_path)
    measurement = measurement_for(os.path.abspath(src_path), {"": [2]}, wall=0.5)
    executor = _FakeExecutor()

    rc, _ = _run_without_coverage_flags(tmp_path, src_path, measurement, executor)

    assert rc == 0
    assert len(executor.calls) == 1


@pytest.mark.component
def test_a_line_no_context_reached_is_uncovered_and_never_mutated_on_a_no_flag_run(tmp_path):
    src_path = _write_source(tmp_path)
    measurement = measurement_for(os.path.abspath(src_path), {"": [9]}, wall=0.5)
    executor = _FakeExecutor()

    rc, _ = _run_without_coverage_flags(tmp_path, src_path, measurement, executor)

    assert rc == 0
    assert executor.calls == []


@pytest.mark.component
def test_a_failing_suite_stops_the_run_before_any_mutant_and_names_the_failing_node(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    src_path = _write_source(tmp_path)
    pytest_args = write_always_failing_pytest_project(str(tmp_path))
    executor = _FakeExecutor()

    rc, _ = _run_without_coverage_flags(tmp_path, src_path, None, executor, pytest_args)

    assert rc == 1
    assert executor.calls == []
    assert "tests/test_always_fails.py::test_fail" in caplog.text


@pytest.mark.component
def test_a_suite_that_collects_no_tests_fails_with_the_no_tests_hint(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    src_path = _write_source(tmp_path)
    os.makedirs(tmp_path / "tests")
    executor = _FakeExecutor()

    rc, _ = _run_without_coverage_flags(tmp_path, src_path, None, executor, ["-q", "tests"])

    assert rc == 1
    assert executor.calls == []
    assert NO_TESTS_HINT in caplog.text


@pytest.mark.component
def test_a_sysmon_measurement_is_refused_with_exit_2_and_names_the_fix(tmp_path, caplog, monkeypatch):
    caplog.set_level(logging.INFO)
    src_path = _write_source(tmp_path)

    def sysmon_measure(**kwargs):
        data = CoverageData(no_disk=True)
        try:
            return measurement_from(data, record_for(core="sysmon"), wall=1.0)
        finally:
            data.close(force=True)

    monkeypatch.setattr("mutate4py._runner.measure_in_scratch", sysmon_measure)
    executor = _FakeExecutor()

    rc, _ = _run_without_coverage_flags(tmp_path, src_path, None, executor)

    assert rc == 2
    assert executor.calls == []
    assert "COVERAGE_CORE" in caplog.text


@pytest.mark.component
def test_a_single_file_run_that_measures_itself_prints_the_measurement_and_overhead_lines(
    tmp_path, caplog, monkeypatch
):
    caplog.set_level(logging.INFO)
    src_path = _write_source(tmp_path)
    measurement = _measured_test(tmp_path, src_path)
    monkeypatch.setattr("mutate4py._runner.measure_in_scratch", lambda **kwargs: measurement)
    executor = _FakeExecutor()

    rc, _ = _run_without_coverage_flags(tmp_path, src_path, None, executor)

    assert rc == 0
    assert "Measurement: 0.50s, 1 tests, core ctrace" in caplog.text
    assert "Per-Mutant overhead:" in caplog.text


class _SurvivingExecutor(_FakeExecutor):
    def run(self, args, timeout):
        self.calls.append(list(args))
        return "survived"


@pytest.mark.component
def test_the_measurement_line_is_set_apart_from_the_survivors_block(tmp_path, caplog, monkeypatch):
    """A reader of the Survivors block stops at the first blank line, so the
    Measurement line, whose wall time varies run to run, must not follow it directly."""
    import mutate4py._execution as execution_mod

    caplog.set_level(logging.INFO)
    src_path = _write_source(tmp_path)
    measurement = _measured_test(tmp_path, src_path)
    monkeypatch.setattr("mutate4py._runner.measure_in_scratch", lambda **kwargs: measurement)
    # The Survivor is confirmed with the full set in a fresh interpreter; this tmp project has no tests,
    # so the confirmation executor is stubbed to let the Survivor stand.
    monkeypatch.setattr(execution_mod, "SubprocessExecutor", lambda cwd, guarded_path: _SurvivingExecutor())

    rc, _ = _run_without_coverage_flags(tmp_path, src_path, None, _SurvivingExecutor())

    assert rc == 3
    lines = "\n".join(caplog.messages).splitlines()
    survivors_at = lines.index("Survivors:")
    measurement_at = next(i for i, ln in enumerate(lines) if ln.startswith("Measurement:"))
    assert "" in lines[survivors_at:measurement_at]


@pytest.mark.component
def test_an_injected_measurement_prints_neither_the_measurement_nor_the_overhead_lines(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    src_path = _write_source(tmp_path)
    measurement = measurement_for(os.path.abspath(src_path), {"": [2]}, wall=0.5)

    rc, _ = _run_without_coverage_flags(tmp_path, src_path, measurement, _FakeExecutor())

    assert rc == 0
    assert "Measurement:" not in caplog.text
    assert "Per-Mutant overhead" not in caplog.text


@pytest.mark.component
def test_a_directory_run_measures_the_suite_once_and_prints_one_batch_summary(tmp_path, caplog, monkeypatch):
    caplog.set_level(logging.INFO)
    ran_log = tmp_path / "ran.log"
    monkeypatch.setenv("MUTATE4PY_FIXTURE_RAN", str(ran_log))
    monkeypatch.chdir(tmp_path)
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "mod_a.py").write_text("X = 1\n")
    (pkg / "mod_b.py").write_text("Y = 2\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "conftest.py").write_text(FIXTURE_CONFTEST)
    (tests / "test_one.py").write_text("def test_one():\n    assert True\n")
    (tests / "test_two.py").write_text("def test_two():\n    assert True\n")
    files = [str(pkg / "mod_a.py"), str(pkg / "mod_b.py")]

    with pytest.raises(SystemExit) as exc:
        _run_files_and_exit(_batch_args(pytest_args=["-q", "tests"]), files)

    assert exc.value.code == 0
    assert sorted(ran_log.read_text().splitlines()) == [
        "tests/test_one.py::test_one",
        "tests/test_two.py::test_two",
    ]
    assert caplog.text.count("Measurement:") == 1
    assert caplog.text.count("Per-Mutant overhead:") == 1
