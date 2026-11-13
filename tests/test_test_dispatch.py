"""Unit tests for the per-Mutant plan builder (`_test_dispatch.plan_mutant`).

`plan_mutant` is pure: given a Site, the run's pytest args, the optional
test-context db, the source path and a TimeoutPolicy, it returns the
MutantPlan (argv, timeout, selection) that both the serial loop and the
parallel Workers dispatch. Expected values are literals, so the assertions
cannot be satisfied by recomputing what the code computes.
"""

import pytest

from mutate4py._discovery import discover_sites
from mutate4py._test_dispatch import MutantPlan, TimeoutPolicy, plan_mutant
from mutate4py._test_dispatch import TestSelectionError as SelectionError

SRC = "/src/calc.py"

# factor x baseline = 3.0 x 2.0 = 6.0, above the 1.0 floor, so the factor term wins.
POLICY = TimeoutPolicy(factor=3.0, min_timeout=1.0, baseline_duration=2.0)


class _FakeTestContextDB:
    def __init__(self, outcome, node_ids=()):
        self._result = (outcome, list(node_ids))

    def tests_for_line(self, source_path, line):
        return self._result


def _one_site(src="def f(a, b):\n    return a > b\n"):
    return discover_sites(src)[0]


def _plan(test_ctx_db, pytest_args=("-q",)):
    return plan_mutant(
        _one_site(),
        pytest_args=list(pytest_args),
        test_ctx_db=test_ctx_db,
        abs_source_path=SRC,
        timeout_policy=POLICY,
    )


@pytest.mark.unit
def test_plan_without_ctx_db_runs_full_args_with_no_selection():
    assert _plan(None) == MutantPlan(args=["-q"], timeout=6.0, selection=None)


@pytest.mark.unit
def test_plan_narrows_to_covering_tests():
    ctx_db = _FakeTestContextDB("narrowed", ["tests/test_calc.py::test_gt"])
    assert _plan(ctx_db) == MutantPlan(
        args=["-q", "tests/test_calc.py::test_gt"],
        timeout=6.0,
        selection="narrowed",
    )


@pytest.mark.unit
def test_plan_static_line_runs_full_args():
    assert _plan(_FakeTestContextDB("static")) == MutantPlan(args=["-q"], timeout=6.0, selection="static")


@pytest.mark.unit
def test_plan_under_listed_runs_full_args_tallied_as_degraded():
    """An under-listed line (issue #69) runs the full args, like "static", but
    is tallied apart so the report can name it."""
    ctx_db = _FakeTestContextDB("under-listed", ["tests/test_calc.py::test_gt"])
    assert _plan(ctx_db) == MutantPlan(args=["-q"], timeout=6.0, selection="degraded")


@pytest.mark.unit
@pytest.mark.parametrize(
    "outcome, hint",
    [
        ("line-absent", "absent from the test-context db"),
        ("file-absent", "not in the test-context db"),
    ],
)
def test_plan_disagreement_raises(outcome, hint):
    with pytest.raises(SelectionError) as excinfo:
        _plan(_FakeTestContextDB(outcome), pytest_args=())
    message = str(excinfo.value)
    assert f"{SRC}:2" in message
    assert hint in message


@pytest.mark.unit
def test_plan_unrecognized_outcome_raises():
    """No outcome may fall through to a full-suite run counted as narrowed."""
    with pytest.raises(SelectionError, match="unrecognized selection outcome"):
        _plan(_FakeTestContextDB("something-new"), pytest_args=())


@pytest.mark.unit
@pytest.mark.parametrize(
    "factor, min_timeout, baseline_duration, expected",
    [
        (3.0, 1.0, 2.0, 6.0),  # factor x baseline above the floor
        (3.0, 10.0, 2.0, 10.0),  # floor above factor x baseline
        (2.5, 0.0, 4.0, 10.0),  # no floor, factor x baseline alone
    ],
)
def test_plan_timeout_is_floored_factor_times_baseline(factor, min_timeout, baseline_duration, expected):
    plan = plan_mutant(
        _one_site(),
        pytest_args=["-q"],
        test_ctx_db=None,
        abs_source_path=SRC,
        timeout_policy=TimeoutPolicy(
            factor=factor,
            min_timeout=min_timeout,
            baseline_duration=baseline_duration,
        ),
    )
    assert plan.timeout == expected
