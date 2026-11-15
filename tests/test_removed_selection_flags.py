"""Issue #101: the selection flags --since-last-run and --lines are removed.
A default run already re-scores only the functions whose code changed (spec #89,
the one Measurement), and a function is re-scored by editing it or by
--mutate-all. Each removed flag is refused at the CLI with exit 2 and a message
naming it, the same refusal #99 and #100 give the coverage and test-context
flags, and it is hidden from --help. The seam is `main()` with argv: the refusal
and the help text are observed from outside the module that implements them."""

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
    (
        ["--lines", "1"],
        "--lines removed in 0.3.0: re-score a function by editing it",
    ),
    (
        ["--since-last-run"],
        "--since-last-run removed in 0.3.0: a default run already re-scores only changed functions",
    ),
    (
        ["--mutate-all"],
        "--mutate-all removed in 0.3.0: a run scores every changed or Unscored function itself",
    ),
]
REMOVED_IDS = ["lines", "since-last-run", "mutate-all"]


@pytest.mark.unit
@pytest.mark.parametrize("flag_args,message", REMOVED_FLAGS, ids=REMOVED_IDS)
def test_removed_selection_flag_exits_2_naming_the_flag(tmp_path, monkeypatch, capsys, flag_args, message):
    p = tmp_path / "s.py"
    p.write_text("x = a > b\n")
    monkeypatch.setattr(sys, "argv", ["mutate4py", str(p), *flag_args])
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 2
    stderr = capsys.readouterr().err
    assert message in stderr


@pytest.mark.unit
@pytest.mark.parametrize("flag_args,message", REMOVED_FLAGS, ids=REMOVED_IDS)
def test_removed_selection_flag_refused_before_any_measurement(tmp_path, monkeypatch, flag_args, message):
    p = tmp_path / "s.py"
    p.write_text("x = a > b\n")
    monkeypatch.setattr(sys, "argv", ["mutate4py", str(p), *flag_args])
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 2


@pytest.mark.unit
def test_removed_selection_flags_are_hidden_from_help(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["mutate4py", "--help"])
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--lines" not in out
    assert "--since-last-run" not in out
    assert "--mutate-all" not in out
