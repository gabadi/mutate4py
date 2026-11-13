"""Unit tests for the directory run's single Measurement (_dispatch.py).

A directory run measures its targets once, before any file is dispatched.
These tests pin when that Measurement is taken, what it is handed, and how a
coverage error, a failed suite and a refused coverage core exit the batch.
"""

import os

import pytest

from ._dispatch_helpers import make_args


@pytest.mark.unit
def test_needs_measurement_true_for_normal_run():
    from mutate4py._dispatch import _needs_measurement

    args = make_args()
    assert _needs_measurement(["a.py"], args) is True


@pytest.mark.unit
def test_needs_measurement_false_when_no_files():
    from mutate4py._dispatch import _needs_measurement

    args = make_args()
    assert _needs_measurement([], args) is False


@pytest.mark.unit
@pytest.mark.parametrize("extra", [{"scan": True}, {"update_manifest": True}, {"check_manifest": True}])
def test_needs_measurement_false_for_no_run_modes(extra):
    from mutate4py._dispatch import _needs_measurement

    args = make_args(**extra)
    assert _needs_measurement(["a.py"], args) is False


@pytest.mark.unit
def test_prepare_directory_measurement_measures_every_file_once(monkeypatch):
    from mutate4py._dispatch import _prepare_directory_measurement

    calls = []
    sentinel = object()

    def fake_measure_in_scratch(*, cwd, pytest_args, target_files):
        calls.append((cwd, list(pytest_args), target_files))
        return sentinel

    monkeypatch.setattr("mutate4py._dispatch.measure_in_scratch", fake_measure_in_scratch)

    result = _prepare_directory_measurement(make_args(pytest_args=["-q"]), ["a.py", "b.py"], "/cwd")

    assert result is sentinel
    assert calls == [("/cwd", ["-q"], (os.path.abspath("a.py"), os.path.abspath("b.py")))]


@pytest.mark.unit
def test_prepare_directory_measurement_acquires_coverage_before_measuring(monkeypatch):
    from mutate4py._dispatch import _prepare_directory_measurement

    order = []
    monkeypatch.setattr("mutate4py._coverage.acquire_coverage", lambda **kwargs: order.append("coverage"))
    monkeypatch.setattr("mutate4py._dispatch.measure_in_scratch", lambda **kwargs: order.append("measure"))

    _prepare_directory_measurement(make_args(lcov="cov.lcov"), ["a.py"], "/cwd")

    assert order == ["coverage", "measure"]


@pytest.mark.unit
def test_prepare_directory_measurement_coverage_error_exits_1(monkeypatch, caplog):
    from mutate4py._coverage import CoverageError
    from mutate4py._dispatch import _prepare_directory_measurement

    def raise_coverage_error(**kwargs):
        raise CoverageError("no coverage source")

    def must_not_measure(**kwargs):
        raise AssertionError("the suite must not run when coverage fails")

    monkeypatch.setattr("mutate4py._coverage.acquire_coverage", raise_coverage_error)
    monkeypatch.setattr("mutate4py._dispatch.measure_in_scratch", must_not_measure)

    with pytest.raises(SystemExit) as exc:
        _prepare_directory_measurement(make_args(lcov="cov.lcov"), ["a.py"], "/cwd")
    assert exc.value.code == 1
    assert "no coverage source" in caplog.text


@pytest.mark.unit
def test_prepare_directory_measurement_failed_suite_exits_1(monkeypatch, caplog):
    from mutate4py._dispatch import _prepare_directory_measurement
    from mutate4py._measurement import MeasurementFailed

    def failing_measure(**kwargs):
        raise MeasurementFailed(failing_node_ids=("tests/test_x.py::test_y",))

    monkeypatch.setattr("mutate4py._dispatch.measure_in_scratch", failing_measure)

    with pytest.raises(SystemExit) as exc:
        _prepare_directory_measurement(make_args(), ["a.py"], "/cwd")
    assert exc.value.code == 1
    assert "tests/test_x.py::test_y" in caplog.text


@pytest.mark.unit
def test_prepare_directory_measurement_sysmon_refused_exits_2(monkeypatch, caplog):
    from mutate4py._dispatch import _prepare_directory_measurement
    from mutate4py._measurement import CoverageCoreRefused

    def refused(**kwargs):
        raise CoverageCoreRefused("sysmon", "set COVERAGE_CORE=ctrace")

    monkeypatch.setattr("mutate4py._dispatch.measure_in_scratch", refused)

    with pytest.raises(SystemExit) as exc:
        _prepare_directory_measurement(make_args(), ["a.py"], "/cwd")
    assert exc.value.code == 2
    assert "sysmon" in caplog.text
