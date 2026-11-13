"""Issue #99: the coverage flags (--cov-cmd, --lcov, --reuse-coverage) are removed.
The run measures coverage itself (the Measurement), so each removed flag is
refused at the CLI with exit 2 and a message naming it. The seam is `main()`
with argv: the refusal, the --scan path and the Coverage gate's source are
observed from outside the module that implements them."""

import sys

import pytest

import mutate4py.__main__ as m


@pytest.fixture(autouse=True)
def no_measurement(monkeypatch, tmp_path):
    """Every test here runs in tmp_path and runs no Measurement: a run from the
    repo's cwd (or an unfaked Measurement) runs the repo's own suite in a nested
    session, which reaches these tests again and recurses."""
    monkeypatch.chdir(tmp_path)

    def must_not_measure(**kwargs):
        raise AssertionError("this test must not measure")

    monkeypatch.setattr("mutate4py._runner.measure_in_scratch", must_not_measure)


REMOVED_FLAGS = [
    ["--cov-cmd", "pytest --cov"],
    ["--lcov", "cov.info"],
    ["--reuse-coverage"],
]


@pytest.mark.unit
@pytest.mark.parametrize("flag_args", REMOVED_FLAGS, ids=["cov-cmd", "lcov", "reuse-coverage"])
def test_removed_coverage_flag_exits_2_naming_the_flag(tmp_path, monkeypatch, capsys, flag_args):
    p = tmp_path / "s.py"
    p.write_text("x = a > b\n")
    monkeypatch.setattr(sys, "argv", ["mutate4py", str(p), *flag_args])
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 2
    stderr = capsys.readouterr().err
    assert f"{flag_args[0]} removed in 0.3.0: the run measures coverage itself" in stderr


@pytest.mark.unit
@pytest.mark.parametrize("flag_args", REMOVED_FLAGS, ids=["cov-cmd", "lcov", "reuse-coverage"])
def test_removed_coverage_flag_refused_before_any_measurement(tmp_path, monkeypatch, flag_args):
    p = tmp_path / "s.py"
    p.write_text("x = a > b\n")
    monkeypatch.setattr(sys, "argv", ["mutate4py", str(p), *flag_args])
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 2


@pytest.mark.unit
def test_scan_runs_without_measurement(tmp_path, monkeypatch, capsys):
    # --scan is coverage-free: it counts sites and never measures (the autouse fixture).
    p = tmp_path / "s.py"
    p.write_text("def f(a, b):\n    return a > b\n")
    monkeypatch.setattr(sys, "argv", ["mutate4py", str(p), "--scan"])
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 0
    assert "Mutation scan" in capsys.readouterr().out


@pytest.mark.unit
def test_coverage_module_is_gone():
    import importlib.util

    assert importlib.util.find_spec("mutate4py._coverage") is None
