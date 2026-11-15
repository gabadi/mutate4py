"""A directory run's closing summary sums every file's Time line and prints the run's total wall time.

The run takes its executors from fakes and its Measurement from in-memory
coverage data, so no pytest session runs; report text is asserted through
caplog, because the run's report blocks go through logging.
"""

import logging
import os
import re

import pytest
from coverage import CoverageData

from ._measurement_helpers import record_for
from .test_measurement_gate import SRC, _batch_args, _run_without_coverage_flags
from mutate4py._dispatch import _run_files_and_exit
from mutate4py._executor import ExecutorDescription, MutantTiming
from mutate4py._measurement import measurement_from

TIME_LINE = re.compile(
    r"Time: mutants \d+\.\d\ds \((\d+)\), timeouts \d+\.\d\ds \((\d+)\), "
    r"confirmation \d+\.\d\ds \((\d+) run, (\d+) kills\)"
)
WALL_LINE = re.compile(r"^Wall: \d+\.\d\ds$", re.MULTILINE)


class _StatusExecutor:
    """Reports every Mutant with the status it was built with."""

    def __init__(self, status: str) -> None:
        self.status = status

    def prime(self) -> None:
        pass

    def run(self, args, timeout, *, control=False):
        return self.status

    def describe(self) -> ExecutorDescription:
        return ExecutorDescription(mode="subprocess", reason="--no-fork")


def _two_file_project(tmp_path) -> list[str]:
    files = []
    for name in ("calc_a.py", "calc_b.py"):
        path = tmp_path / name
        path.write_text(SRC)
        files.append(str(path))
    return files


def _measurement_over(files: list[str]):
    data = CoverageData(no_disk=True)
    try:
        data.set_context("")
        for path in files:
            data.add_lines({os.path.abspath(path): [2]})
        return measurement_from(data, record_for(), wall=0.5)
    finally:
        data.close(force=True)


@pytest.mark.unit
def test_a_run_adds_its_timing_to_the_sink_it_is_given(tmp_path):
    src_path = str(tmp_path / "calc.py")
    (tmp_path / "calc.py").write_text(SRC)
    sink = MutantTiming()
    measurement = _measurement_over([src_path])

    rc, _ = _run_without_coverage_flags(tmp_path, src_path, measurement, _StatusExecutor("killed"), timing_sink=sink)

    assert rc == 0
    assert (sink.mutants_count, sink.timeouts_count, sink.confirmation_runs) == (1, 0, 0)


@pytest.mark.unit
def test_a_directory_run_sums_the_time_line_across_its_files_and_prints_the_wall_time(tmp_path, caplog, monkeypatch):
    caplog.set_level(logging.INFO)
    monkeypatch.chdir(tmp_path)
    files = _two_file_project(tmp_path)
    measurement = _measurement_over(files)
    monkeypatch.setattr("mutate4py._dispatch.measure_in_scratch", lambda **kwargs: measurement)
    monkeypatch.setattr("mutate4py._runner.select_executor", lambda **kwargs: _StatusExecutor("timeout"))

    with pytest.raises(SystemExit) as exc:
        _run_files_and_exit(_batch_args(), files)

    assert exc.value.code == 0
    time_lines = [ln for ln in caplog.text.splitlines() if ln.startswith("Time:")]
    assert len(time_lines) == 3  # one per file, then the batch's
    assert [TIME_LINE.fullmatch(ln).groups() for ln in time_lines] == [
        ("0", "1", "0", "0"),
        ("0", "1", "0", "0"),
        ("0", "2", "0", "0"),
    ]
    assert len(WALL_LINE.findall(caplog.text)) == 1
    assert caplog.text.index("Wall:") > caplog.text.rindex("Time:")
