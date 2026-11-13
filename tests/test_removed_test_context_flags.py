"""Issue #100: the test-context db flags (--test-contexts, --build-test-contexts)
are removed. Narrowing now comes from the one Measurement (spec #89), so each
removed flag is refused at the CLI with exit 2 and a message naming it, the
same refusal #99 gives the coverage flags. The seam is `main()` with argv: the
refusal is observed from outside the module that implements it, and the
isolated-session test-context modules are gone from the package."""

import importlib.util
import sys

import pytest

import mutate4py.__main__ as m


@pytest.fixture(autouse=True)
def no_measurement(monkeypatch, tmp_path):
    """Every test here runs in tmp_path and runs no Measurement: a run from the
    repo's cwd would run the repo's own suite in a nested session."""
    monkeypatch.chdir(tmp_path)

    def must_not_measure(**kwargs):
        raise AssertionError("this test must not measure")

    monkeypatch.setattr("mutate4py._runner.measure_in_scratch", must_not_measure)


REMOVED_FLAGS = [
    ["--test-contexts", "tests.coverage"],
    ["--build-test-contexts", "out.coverage"],
]


@pytest.mark.unit
@pytest.mark.parametrize("flag_args", REMOVED_FLAGS, ids=["test-contexts", "build-test-contexts"])
def test_removed_test_context_flag_exits_2_naming_the_flag(tmp_path, monkeypatch, capsys, flag_args):
    p = tmp_path / "s.py"
    p.write_text("x = a > b\n")
    monkeypatch.setattr(sys, "argv", ["mutate4py", str(p), *flag_args])
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 2
    stderr = capsys.readouterr().err
    assert f"{flag_args[0]} removed in 0.3.0: the run measures coverage itself" in stderr


@pytest.mark.unit
@pytest.mark.parametrize("flag_args", REMOVED_FLAGS, ids=["test-contexts", "build-test-contexts"])
def test_removed_test_context_flag_refused_before_any_measurement(tmp_path, monkeypatch, flag_args):
    p = tmp_path / "s.py"
    p.write_text("x = a > b\n")
    monkeypatch.setattr(sys, "argv", ["mutate4py", str(p), *flag_args])
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 2


@pytest.mark.unit
def test_test_context_flag_refused_even_when_its_file_is_missing(tmp_path, monkeypatch, capsys):
    # The removed flag is refused on its own, not reported as a missing db file.
    p = tmp_path / "s.py"
    p.write_text("x = a > b\n")
    monkeypatch.setattr(sys, "argv", ["mutate4py", str(p), "--test-contexts", "absent.coverage"])
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 2
    stderr = capsys.readouterr().err
    assert "--test-contexts removed in 0.3.0" in stderr
    assert "file not found" not in stderr


@pytest.mark.unit
@pytest.mark.parametrize(
    "module",
    [
        "mutate4py._test_selection",
        "mutate4py._test_context_build",
        "mutate4py._test_context_cache",
        "mutate4py._test_context_orchestration",
        "mutate4py._test_collection",
    ],
)
def test_test_context_module_is_gone(module):
    assert importlib.util.find_spec(module) is None
