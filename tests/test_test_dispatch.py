"""Unit tests for the per-Mutant dispatch planning of `_test_dispatch`.

`plan_mutant` is pure but for the node id file check: given a Site, the run's pytest args, the run's
explicit positional path args, the optional selection source, the source path and a TimeoutPolicy, it
returns the MutantPlan (argv, timeout, selection) that both the serial loop and the parallel Workers
dispatch. Expected values are literals, so the assertions cannot be satisfied by recomputing what the
code computes. `ControlRuns.settle` decides what a Mutant that ends in pytest exit 4 or 5 is, with the
Control run it makes on the original code.
"""

import pytest

from mutate4py._discovery import discover_sites
from mutate4py._test_dispatch import (
    ControlRuns,
    ControlTarget,
    MutantPlan,
    NoTestsCollectedError,
    PlanInputs,
    TimeoutPolicy,
    confirm_plan,
    plan_mutant,
)

from ._scripted_executor import ScriptedExecutor

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


# -- The Control run: a Mutant that ends in pytest exit 4 or 5 ---------------------------------

_PLAN = MutantPlan(args=["-q", GT], timeout=6.0, selection="narrowed")


def _settle(tmp_path, status, control_answers=(), controls=None, plan=_PLAN):
    """Settle `status` for the one Site of _one_site() against a file that holds the Mutant's source.

    Returns (what settle gave, the executor, which records each Control run: argv, timeout and source)."""
    path = tmp_path / "calc.py"
    path.write_text("mutated\n")
    executor = ScriptedExecutor(str(path), control_answers)
    target = ControlTarget(str(path), "original\n", executor, SRC)
    controls = ControlRuns() if controls is None else controls
    return controls.settle(status, plan, _one_site(), target), executor


@pytest.mark.unit
@pytest.mark.parametrize("status", ["killed", "survived", "timeout"])
def test_settle_leaves_a_classification_that_is_not_exit_4_or_5_alone_and_runs_no_control(tmp_path, status):
    settled, executor = _settle(tmp_path, status)
    assert settled == status
    assert executor.calls == []


@pytest.mark.unit
def test_settle_counts_a_mutant_that_ends_abnormally_as_killed_and_runs_no_control(tmp_path):
    """Exit 2 or 3, a signal, a pytest that did not start: the Executor says `errored`. For a Mutant
    that is a kill (ADR 0011), and it is no exit 4 or 5 that a Control run must explain."""
    settled, executor = _settle(tmp_path, "errored")
    assert settled == "killed"
    assert executor.calls == []


@pytest.mark.unit
@pytest.mark.parametrize("status", ["usage-error", "no-tests-collected"])
@pytest.mark.parametrize("control", ["survived", "killed"])
def test_settle_kills_a_mutant_whose_control_run_ran_tests(tmp_path, status, control):
    """The same argv ran tests on the original code, so the Mutant broke the run: it is killed.
    The Control run puts the original source back first, then runs the plan as planned."""
    settled, executor = _settle(tmp_path, status, [control])
    assert settled == "killed"
    assert executor.calls == [(["-q", GT], 6.0)]
    assert executor.seen_sources == ["original\n"]
    assert executor.controls == [True]


_CONTROL_ENDS = [
    ("usage-error", "exited with a usage error (exit 4)"),
    ("no-tests-collected", "collected no tests (exit 5)"),
    ("timeout", "timed out after 6s"),
    ("errored", "ended with no test result"),
]


@pytest.mark.unit
@pytest.mark.parametrize("status", ["usage-error", "no-tests-collected"])
@pytest.mark.parametrize(("control", "ended"), _CONTROL_ENDS)
def test_settle_aborts_and_says_what_the_control_run_gave_when_it_ran_no_test(tmp_path, status, control, ended):
    """A Control run on the original code ran, and its end shows no test ran. The abort names the Site,
    says a Control run on the original code ran, and says how it ended."""
    with pytest.raises(NoTestsCollectedError) as excinfo:
        _settle(tmp_path, status, [control])
    message = str(excinfo.value)
    assert message.startswith(f"{SRC}:2: ")
    assert f"A Control run of the same pytest args on the original code {ended}" in message


@pytest.mark.unit
@pytest.mark.parametrize("control", ["timeout", "errored"])
def test_settle_does_not_blame_the_args_when_the_control_run_proved_nothing(tmp_path, control):
    """A Control run that timed out or crashed says nothing of the args. The abort says so, instead of
    leaving only the Mutant's own exit, which tells the user to check --pytest-args for a fine argv."""
    with pytest.raises(NoTestsCollectedError, match="did not show whether the args or the Mutant caused"):
        _settle(tmp_path, "usage-error", [control])


@pytest.mark.unit
@pytest.mark.parametrize("control", ["usage-error", "no-tests-collected"])
def test_settle_blames_the_args_when_the_control_run_ends_in_exit_4_or_5_too(tmp_path, control):
    with pytest.raises(NoTestsCollectedError) as excinfo:
        _settle(tmp_path, "usage-error", [control])
    assert "check --pytest-args" in str(excinfo.value)
    assert "did not show" not in str(excinfo.value)


@pytest.mark.unit
def test_settle_keeps_the_hint_of_the_exit_the_mutant_ended_in(tmp_path):
    with pytest.raises(NoTestsCollectedError, match="pytest collected no tests to run"):
        _settle(tmp_path, "no-tests-collected", ["timeout"])


@pytest.mark.unit
def test_settle_clears_no_argv_on_a_control_run_that_proved_nothing(tmp_path):
    """With a bad argv, one Control run that ended in a signal must not clear the argv: every later
    exit 4 of it would be scored killed while no test ran, a false win."""
    controls = ControlRuns()

    for answer in ["errored", "usage-error"]:
        with pytest.raises(NoTestsCollectedError):
            _settle(tmp_path, "usage-error", [answer], controls=controls)

    assert controls.cleared == set()


@pytest.mark.unit
def test_settle_runs_one_control_per_argv_once_it_ran_tests(tmp_path):
    controls = ControlRuns()
    other = MutantPlan(args=["-q", "other"], timeout=6.0, selection=None)

    first, executor = _settle(tmp_path, "usage-error", ["survived"], controls=controls)
    second, again = _settle(tmp_path, "no-tests-collected", [], controls=controls)
    third, other_executor = _settle(tmp_path, "usage-error", ["survived"], controls=controls, plan=other)

    assert (first, second, third) == ("killed", "killed", "killed")
    assert len(executor.calls) == 1
    assert again.calls == []
    assert other_executor.calls == [(["-q", "other"], 6.0)]
