"""Unit tests for the per-Mutant plan builder (`_test_dispatch.plan_mutant`).

`plan_mutant` is pure: given a Site, the run's pytest args, the run's explicit
positional path args, the optional selection source, the source path and a
TimeoutPolicy, it returns the MutantPlan (argv, timeout, selection) that both the
serial loop and the parallel Workers dispatch. Expected values are literals, so
the assertions cannot be satisfied by recomputing what the code computes.
"""

import pytest

from mutate4py._discovery import discover_sites
from mutate4py._test_dispatch import (
    ControlRuns,
    MutantPlan,
    NoTestsCollectedError,
    PlanInputs,
    TimeoutPolicy,
    confirm_plan,
    control_run,
    plan_mutant,
)

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


@pytest.fixture
def project(tmp_path):
    """The run directory a plan is built for: it holds the test file that GT names."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_calc.py").write_text("def test_gt():\n    assert True\n")
    return str(tmp_path)


def _one_site(src="def f(a, b):\n    return a > b\n"):
    return discover_sites(src)[0]


def _plan(cwd, selection_source, pytest_args=("-q",), positionals=(), timeout_policy=None):
    inputs = PlanInputs(
        pytest_args=list(pytest_args),
        selection_source=selection_source,
        abs_source_path=SRC,
        timeout_policy=_policy() if timeout_policy is None else timeout_policy,
        positionals=tuple(positionals),
        cwd=cwd,
    )
    return plan_mutant(_one_site(), inputs)


@pytest.mark.unit
def test_plan_without_a_selection_source_runs_full_args_with_no_selection(project):
    assert _plan(project, None) == MutantPlan(args=["-q"], timeout=15.0, selection=None)


@pytest.mark.unit
def test_plan_narrows_to_covering_tests(project):
    source = _FakeSelectionSource("narrowed", [GT])
    assert _plan(project, source) == MutantPlan(args=["-q", GT], timeout=6.0, selection="narrowed")


@pytest.mark.unit
def test_plan_narrowed_replaces_an_explicit_positional_path_with_the_node_ids(project):
    """A positional test path would otherwise run the whole path beside the node ids (issue #96)."""
    source = _FakeSelectionSource("narrowed", [GT])
    assert _plan(project, source, pytest_args=("-q", "tests"), positionals=("tests",)) == MutantPlan(
        args=["-q", GT], timeout=6.0, selection="narrowed"
    )


@pytest.mark.unit
def test_plan_keeps_an_option_value_spelled_like_a_positional(project):
    """`-k tests` filters by name; only the bare `tests` after it is the positional."""
    source = _FakeSelectionSource("narrowed", [GT])
    assert _plan(project, source, pytest_args=("-k", "tests", "tests"), positionals=("tests",)) == MutantPlan(
        args=["-k", "tests", GT], timeout=6.0, selection="narrowed"
    )


@pytest.mark.unit
def test_plan_with_no_positionals_keeps_every_arg_when_narrowing(project):
    source = _FakeSelectionSource("narrowed", [GT])
    assert _plan(project, source, pytest_args=("-k", "tests")) == MutantPlan(
        args=["-k", "tests", GT], timeout=6.0, selection="narrowed"
    )


@pytest.mark.unit
def test_plan_static_line_runs_full_args(project):
    assert _plan(project, _FakeSelectionSource("static")) == MutantPlan(args=["-q"], timeout=15.0, selection="static")


@pytest.mark.unit
def test_plan_static_line_keeps_the_positional_path(project):
    """A static Mutant runs the full set exactly as the run was asked to."""
    assert _plan(
        project, _FakeSelectionSource("static"), pytest_args=("-q", "tests"), positionals=("tests",)
    ) == MutantPlan(args=["-q", "tests"], timeout=15.0, selection="static")


@pytest.mark.unit
def test_plan_uncovered_line_runs_full_args_tallied_as_static(project):
    """An uncovered line (a Coverage gate flagged it, the Measurement did not reach it) runs the
    full set, tallied as "static": the Measurement has no covering test to name for it."""
    assert _plan(project, _FakeSelectionSource("uncovered")) == MutantPlan(
        args=["-q"], timeout=15.0, selection="static"
    )


@pytest.mark.unit
@pytest.mark.parametrize("outcome", ["something-new", "under-listed", "line-absent", "file-absent"])
def test_plan_unrecognized_outcome_raises(outcome, project):
    """No outcome may fall through to a full-suite run counted as narrowed. The retired
    db outcomes (under-listed, line-absent, file-absent) are unrecognized now, so they refuse too."""
    with pytest.raises(ValueError, match="unrecognized selection outcome") as excinfo:
        _plan(project, _FakeSelectionSource(outcome), pytest_args=())
    assert f"{SRC}:2" in str(excinfo.value)


@pytest.mark.unit
def test_the_full_set_is_budgeted_as_none_and_a_narrowed_mutant_by_its_node_ids(project):
    budgeted = []

    def recording_budget(node_ids):
        budgeted.append(node_ids)
        return 1.0

    policy = TimeoutPolicy(factor=1.0, min_timeout=0.0, overhead=0.0, budget_of=recording_budget)
    _plan(project, _FakeSelectionSource("narrowed", [GT]), timeout_policy=policy)
    _plan(project, _FakeSelectionSource("static"), timeout_policy=policy)

    assert budgeted == [frozenset({GT}), None]


@pytest.mark.unit
def test_plan_timeout_adds_the_per_mutant_overhead_to_the_budget(project):
    policy = TimeoutPolicy(factor=3.0, min_timeout=1.0, overhead=0.5, budget_of=_budget_of)
    assert _plan(project, _FakeSelectionSource("narrowed", [GT]), timeout_policy=policy).timeout == 6.5


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
        cwd="/proj",
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


@pytest.mark.unit
def test_plan_narrowed_aborts_when_a_node_id_names_a_file_that_is_not_under_the_run_directory(project):
    """The Measurement records node ids relative to its pytest rootdir. From any other directory pytest
    exits 4 on them, so the run aborts before any Mutant, not by a race with the Mutant timeout."""
    source = _FakeSelectionSource("narrowed", ["member/tests/test_calc.py::test_gt"])
    with pytest.raises(NoTestsCollectedError) as excinfo:
        _plan(project, source)
    message = str(excinfo.value)
    assert f"{SRC}:2" in message
    assert "member/tests/test_calc.py::test_gt" in message
    assert project in message


@pytest.mark.unit
def test_plan_narrowed_checks_every_node_id_not_only_the_first(project):
    source = _FakeSelectionSource("narrowed", [GT, "tests/test_gone.py::test_gt"])
    with pytest.raises(NoTestsCollectedError, match="tests/test_gone.py::test_gt"):
        _plan(project, source)


@pytest.mark.unit
def test_plan_static_line_names_no_node_id_so_no_path_is_checked(tmp_path):
    assert _plan(str(tmp_path), _FakeSelectionSource("static")) == MutantPlan(
        args=["-q"], timeout=15.0, selection="static"
    )


# -- The control run: a Mutant that ends in pytest exit 4 or 5 ---------------------------------


def _no_control():
    raise AssertionError("no control run was due")


@pytest.mark.unit
@pytest.mark.parametrize("status", ["killed", "survived", "timeout"])
def test_settle_leaves_a_classification_that_is_not_exit_4_or_5_alone_and_runs_no_control(status):
    assert ControlRuns().settle(status, ["-q"], _no_control) == status


@pytest.mark.unit
@pytest.mark.parametrize("status", ["usage-error", "no-tests-collected"])
@pytest.mark.parametrize("control", ["survived", "killed"])
def test_settle_kills_a_mutant_whose_control_run_ran_tests(status, control):
    """The same argv ran tests on the original code, so the Mutant broke the run: it is killed."""
    assert ControlRuns().settle(status, ["-q"], lambda: control) == "killed"


@pytest.mark.unit
@pytest.mark.parametrize("status", ["usage-error", "no-tests-collected"])
@pytest.mark.parametrize("control", ["usage-error", "no-tests-collected", "timeout"])
def test_settle_keeps_the_exit_when_the_control_run_ran_no_test(status, control):
    """The original code ends the same way, or cannot show it: the argv may be the defect, so the exit stays."""
    assert ControlRuns().settle(status, ["-q"], lambda: control) == status


@pytest.mark.unit
def test_settle_runs_one_control_per_argv_once_it_ran_tests():
    runs = []

    def control():
        runs.append("run")
        return "survived"

    controls = ControlRuns()
    assert controls.settle("usage-error", ["-q", "a"], control) == "killed"
    assert controls.settle("no-tests-collected", ["-q", "a"], control) == "killed"
    assert runs == ["run"]
    assert controls.settle("usage-error", ["-q", "b"], control) == "killed"
    assert runs == ["run", "run"]


@pytest.mark.unit
def test_settle_does_not_remember_a_control_run_that_ran_no_test():
    runs = []

    def control():
        runs.append("run")
        return "usage-error"

    controls = ControlRuns()
    assert controls.settle("usage-error", ["-q"], control) == "usage-error"
    assert controls.settle("usage-error", ["-q"], control) == "usage-error"
    assert runs == ["run", "run"]


class _SourceSpy:
    """An Executor that records the argv, the timeout and the guarded file's text at each run."""

    def __init__(self, path, status):
        self._path = path
        self._status = status
        self.runs = []

    def run(self, args, timeout):
        with open(self._path) as f:
            self.runs.append((args, timeout, f.read()))
        return self._status


@pytest.mark.unit
def test_control_run_restores_the_original_source_then_runs_the_plan_as_planned(tmp_path):
    path = tmp_path / "calc.py"
    path.write_text("mutated\n")
    executor = _SourceSpy(str(path), "survived")

    status = control_run(
        str(path), "original\n", executor, MutantPlan(args=["-q", GT], timeout=6.0, selection="narrowed")
    )

    assert status == "survived"
    assert executor.runs == [(["-q", GT], 6.0, "original\n")]
