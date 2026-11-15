"""Unit tests for the per-Mutant plan builder (`_test_dispatch.plan_mutant`).

`plan_mutant` is pure: given a Site, the run's pytest args, the run's explicit
positional path args, the optional selection source, the source path and a
TimeoutPolicy, it returns the MutantPlan (argv, timeout, selection) that both the
serial loop and the parallel Workers dispatch. Expected values are literals, so
the assertions cannot be satisfied by recomputing what the code computes.
"""

import pytest

from mutate4py._discovery import discover_sites
from mutate4py._test_dispatch import MutantPlan, PlanInputs, TimeoutPolicy, confirm_plan, plan_mutant

SRC = "/src/calc.py"
GT = "tests/test_calc.py::test_gt"


def _budget_of(node_ids):
    """The Mutant's own tests budget 2.0 s; the full test set (None) budgets 5.0 s.

    Any other node-id set is a bug in the planner, so it budgets a sentinel 99.0.
    """
    if node_ids is None:
        return 5.0
    return 2.0 if node_ids == frozenset({GT}) else 99.0


def _policy() -> TimeoutPolicy:
    """factor x budget: 3 x 2.0 = 6.0 for the Mutant's own tests, 3 x 5.0 = 15.0 for the full set."""
    return TimeoutPolicy(factor=3.0, min_timeout=1.0, overhead=0.0, budget_of=_budget_of)


class _FakeSelectionSource:
    def __init__(self, outcome, node_ids=()):
        self._result = (outcome, list(node_ids))

    def tests_for_line(self, source_path, line):
        return self._result


def _one_site(src="def f(a, b):\n    return a > b\n"):
    return discover_sites(src)[0]


def _plan(selection_source, pytest_args=("-q",), positionals=(), timeout_policy=None):
    inputs = PlanInputs(
        pytest_args=list(pytest_args),
        selection_source=selection_source,
        abs_source_path=SRC,
        timeout_policy=_policy() if timeout_policy is None else timeout_policy,
        positionals=tuple(positionals),
    )
    return plan_mutant(_one_site(), inputs)


@pytest.mark.unit
def test_plan_without_a_selection_source_runs_full_args_with_no_selection():
    assert _plan(None) == MutantPlan(args=["-q"], timeout=15.0, selection=None)


@pytest.mark.unit
def test_plan_narrows_to_covering_tests():
    source = _FakeSelectionSource("narrowed", [GT])
    assert _plan(source) == MutantPlan(args=["-q", GT], timeout=6.0, selection="narrowed")


@pytest.mark.unit
def test_plan_narrowed_replaces_an_explicit_positional_path_with_the_node_ids():
    """A positional test path would otherwise run the whole path beside the node ids (issue #96)."""
    source = _FakeSelectionSource("narrowed", [GT])
    assert _plan(source, pytest_args=("-q", "tests"), positionals=("tests",)) == MutantPlan(
        args=["-q", GT], timeout=6.0, selection="narrowed"
    )


@pytest.mark.unit
def test_plan_keeps_an_option_value_spelled_like_a_positional():
    """`-k tests` filters by name; only the bare `tests` after it is the positional."""
    source = _FakeSelectionSource("narrowed", [GT])
    assert _plan(source, pytest_args=("-k", "tests", "tests"), positionals=("tests",)) == MutantPlan(
        args=["-k", "tests", GT], timeout=6.0, selection="narrowed"
    )


@pytest.mark.unit
def test_plan_with_no_positionals_keeps_every_arg_when_narrowing():
    source = _FakeSelectionSource("narrowed", [GT])
    assert _plan(source, pytest_args=("-k", "tests")) == MutantPlan(
        args=["-k", "tests", GT], timeout=6.0, selection="narrowed"
    )


@pytest.mark.unit
def test_plan_static_line_runs_full_args():
    assert _plan(_FakeSelectionSource("static")) == MutantPlan(args=["-q"], timeout=15.0, selection="static")


@pytest.mark.unit
def test_plan_static_line_keeps_the_positional_path():
    """A static Mutant runs the full set exactly as the run was asked to."""
    assert _plan(_FakeSelectionSource("static"), pytest_args=("-q", "tests"), positionals=("tests",)) == MutantPlan(
        args=["-q", "tests"], timeout=15.0, selection="static"
    )


@pytest.mark.unit
def test_plan_uncovered_line_runs_full_args_tallied_as_static():
    """An uncovered line (a Coverage gate flagged it, the Measurement did not reach it) runs the
    full set, tallied as "static": the Measurement has no covering test to name for it."""
    assert _plan(_FakeSelectionSource("uncovered")) == MutantPlan(args=["-q"], timeout=15.0, selection="static")


@pytest.mark.unit
@pytest.mark.parametrize("outcome", ["something-new", "under-listed", "line-absent", "file-absent"])
def test_plan_unrecognized_outcome_raises(outcome):
    """No outcome may fall through to a full-suite run counted as narrowed. The retired
    db outcomes (under-listed, line-absent, file-absent) are unrecognized now, so they refuse too."""
    with pytest.raises(ValueError, match="unrecognized selection outcome") as excinfo:
        _plan(_FakeSelectionSource(outcome), pytest_args=())
    assert f"{SRC}:2" in str(excinfo.value)


@pytest.mark.unit
def test_the_full_set_is_budgeted_as_none_and_a_narrowed_mutant_by_its_node_ids():
    budgeted = []

    def recording_budget(node_ids):
        budgeted.append(node_ids)
        return 1.0

    policy = TimeoutPolicy(factor=1.0, min_timeout=0.0, overhead=0.0, budget_of=recording_budget)
    _plan(_FakeSelectionSource("narrowed", [GT]), timeout_policy=policy)
    _plan(_FakeSelectionSource("static"), timeout_policy=policy)

    assert budgeted == [frozenset({GT}), None]


@pytest.mark.unit
def test_plan_timeout_adds_the_per_mutant_overhead_to_the_budget():
    policy = TimeoutPolicy(factor=3.0, min_timeout=1.0, overhead=0.5, budget_of=_budget_of)
    assert _plan(_FakeSelectionSource("narrowed", [GT]), timeout_policy=policy).timeout == 6.5


@pytest.mark.unit
@pytest.mark.parametrize(
    "factor, min_timeout, budget, overhead, expected",
    [
        (3.0, 1.0, 2.0, 0.0, 6.0),  # factor x budget above the floor
        (3.0, 10.0, 2.0, 0.0, 10.0),  # floor above factor x budget
        (2.5, 0.0, 4.0, 0.0, 10.0),  # no floor, factor x budget alone
        (3.0, 1.0, 2.0, 0.9, 6.9),  # overhead added on top of the factor term
        (3.0, 10.0, 2.0, 0.9, 10.9),  # overhead added on top of the floor
    ],
)
def test_plan_timeout_is_floored_factor_times_budget_plus_overhead(factor, min_timeout, budget, overhead, expected):
    inputs = PlanInputs(
        pytest_args=["-q"],
        selection_source=None,
        abs_source_path=SRC,
        timeout_policy=TimeoutPolicy(
            factor=factor,
            min_timeout=min_timeout,
            overhead=overhead,
            budget_of=lambda node_ids: budget,
        ),
        positionals=(),
    )
    plan = plan_mutant(_one_site(), inputs)
    assert plan.timeout == pytest.approx(expected)


@pytest.mark.unit
def test_confirm_plan_runs_the_full_args_verbatim_under_the_full_set_timeout():
    """A Survivor is confirmed with the whole test set: positional path kept, budgeted as None."""
    plan = confirm_plan(["-q", "tests"], _policy())
    assert plan == MutantPlan(args=["-q", "tests"], timeout=15.0, selection=None)


@pytest.mark.unit
def test_confirm_plan_timeout_adds_the_per_mutant_overhead_to_the_full_set_budget():
    policy = TimeoutPolicy(factor=3.0, min_timeout=1.0, overhead=0.5, budget_of=_budget_of)
    assert confirm_plan(["-q"], policy).timeout == 15.5
