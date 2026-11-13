"""Unit tests for the report of a run that skips its Measurement (design 89 §5b).

The skipped run prints the skipped Measurement line, the Survivors its stored Manifests record, and
the Time line, and exits as a scored run would for those Survivors. It prints no Mutation Report.
"""

import os

import pytest

from mutate4py._manifest import build_manifest, reconcile_manifest
from mutate4py._skipped_run import skipped_run_report

TESTED_AT = "2026-01-01T00:00:00Z"
SRC = "def f(a, b):\n    return a > b\n"
CLEAN = {"score": {"killed": 1, "survived": 0, "uncovered": 0}, "survivors": [], "accepted": []}
SURVIVED = {
    "score": {"killed": 0, "survived": 1, "uncovered": 0},
    "survivors": [{"line": 2, "desc": "a > b -> a >= b"}],
    "accepted": [],
}


def _manifest(scores: dict) -> dict:
    return reconcile_manifest(None, build_manifest(SRC, tested_at=TESTED_AT), scores, fingerprint="fp")


@pytest.mark.unit
def test_the_report_names_the_skipped_measurement_and_no_mutation_report(tmp_path):
    lines, _ = skipped_run_report(
        [(str(tmp_path / "calc.py"), _manifest({"func/f": CLEAN}))], cwd=str(tmp_path), allow_survivors=False
    )

    assert "Measurement: skipped (code and tests unchanged since the last scored run)" in lines
    assert not any("Mutation Report" in line for line in lines)


@pytest.mark.unit
def test_a_target_with_no_recorded_survivor_exits_0_and_lists_none(tmp_path):
    lines, code = skipped_run_report(
        [(str(tmp_path / "calc.py"), _manifest({"func/f": CLEAN}))], cwd=str(tmp_path), allow_survivors=False
    )

    assert code == 0
    assert not any("Recorded survivors" in line for line in lines)


@pytest.mark.unit
def test_an_unaccepted_recorded_survivor_is_listed_and_exits_3(tmp_path):
    lines, code = skipped_run_report(
        [(str(tmp_path / "calc.py"), _manifest({"func/f": SURVIVED}))], cwd=str(tmp_path), allow_survivors=False
    )

    assert code == 3
    assert "Recorded survivors (not re-run):" in lines
    assert "  line 2 a > b -> a >= b calc.py func/f" in lines


@pytest.mark.unit
def test_allow_survivors_keeps_the_survivor_listed_and_exits_0(tmp_path):
    lines, code = skipped_run_report(
        [(str(tmp_path / "calc.py"), _manifest({"func/f": SURVIVED}))], cwd=str(tmp_path), allow_survivors=True
    )

    assert code == 0
    assert "  line 2 a > b -> a >= b calc.py func/f" in lines


@pytest.mark.unit
def test_survivors_of_a_batch_are_labelled_with_their_own_file(tmp_path):
    first = os.path.join(str(tmp_path), "first.py")
    second = os.path.join(str(tmp_path), "pkg", "second.py")
    targets = [(first, _manifest({"func/f": SURVIVED})), (second, _manifest({"func/f": SURVIVED}))]

    lines, code = skipped_run_report(targets, cwd=str(tmp_path), allow_survivors=False)

    assert code == 3
    assert "  line 2 a > b -> a >= b first.py func/f" in lines
    assert "  line 2 a > b -> a >= b pkg/second.py func/f" in lines


@pytest.mark.unit
def test_the_report_ends_with_the_time_line_of_a_run_that_ran_no_mutant(tmp_path):
    lines, _ = skipped_run_report(
        [(str(tmp_path / "calc.py"), _manifest({"func/f": CLEAN}))], cwd=str(tmp_path), allow_survivors=False
    )

    assert lines[-1].startswith("Time: mutants 0.00s (0)")
