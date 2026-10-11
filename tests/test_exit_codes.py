"""Unit tests for the exit-code table and batch severity (#76).

Severity runs 2 > 1 > 3 > 0: a survivor (3) never masks a usage or parse
error (2), and a failure (1) outranks a survivor. The batch tests drive
_run_files_and_exit with a fake per-file runner; no subprocess runs.
"""

import argparse

import pytest

from mutate4py._exit_codes import (
    EXIT_OK,
    EXIT_SURVIVORS,
    scored_run_exit_code,
    worse_exit_code,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (2, 3, 2),
        (3, 2, 2),
        (1, 3, 1),
        (3, 1, 1),
        (3, 0, 3),
        (0, 3, 3),
        (2, 1, 2),
        (0, 0, 0),
    ],
)
def test_worse_exit_code_severity_order(a, b, expected):
    assert worse_exit_code(a, b) == expected


@pytest.mark.unit
def test_worse_exit_code_unknown_code_ranks_above_usage():
    assert worse_exit_code(70, 2) == 70


@pytest.mark.unit
def test_scored_run_exit_code_three_with_survivors():
    assert scored_run_exit_code(2, allow_survivors=False) == EXIT_SURVIVORS


@pytest.mark.unit
def test_scored_run_exit_code_zero_without_survivors():
    assert scored_run_exit_code(0, allow_survivors=False) == EXIT_OK


@pytest.mark.unit
def test_scored_run_exit_code_zero_when_allowed():
    assert scored_run_exit_code(2, allow_survivors=True) == EXIT_OK


# ── batch severity through _run_files_and_exit ───────────────────────────────


def _batch_exit_code(monkeypatch, outcomes):
    """Run _run_files_and_exit over files whose per-file outcome is an exit code,
    or None for a file that fails to parse. Returns the SystemExit code."""
    import mutate4py._dispatch as dispatch

    def fake_run_on_file(args, py_file, source, cwd, baseline_duration=None):
        outcome = outcomes[py_file]
        if outcome is None:
            raise SyntaxError("invalid syntax", (py_file, 1, 1, "x"))
        return outcome

    monkeypatch.setattr(dispatch, "_load_source", lambda path: "x = 1\n")
    monkeypatch.setattr(dispatch, "_run_on_file", fake_run_on_file)

    args = argparse.Namespace(scan=True, update_manifest=False, check_manifest=False)
    with pytest.raises(SystemExit) as exc:
        dispatch._run_files_and_exit(args, list(outcomes))
    return exc.value.code


@pytest.mark.unit
def test_batch_parse_failure_outranks_survivor_file(monkeypatch):
    assert _batch_exit_code(monkeypatch, {"a.py": 3, "b.py": None}) == 2


@pytest.mark.unit
@pytest.mark.parametrize(
    "outcomes",
    [{"a.py": 1, "b.py": 3}, {"a.py": 3, "b.py": 1}],
)
def test_batch_failure_outranks_survivor_file(monkeypatch, outcomes):
    assert _batch_exit_code(monkeypatch, outcomes) == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    "outcomes",
    [{"a.py": 0, "b.py": 3}, {"a.py": 3, "b.py": 0}],
)
def test_batch_survivor_file_outranks_clean_file(monkeypatch, outcomes):
    assert _batch_exit_code(monkeypatch, outcomes) == 3
