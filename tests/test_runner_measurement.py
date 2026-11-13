"""Runner wiring for a run handed a Measurement (issue #96): a narrowed Mutant
keeps the Measurement's positional args, and the timeout policy budgets the
full set as the Measurement's ALL plus the measured Per-Mutant overhead.
"""

import pytest


@pytest.mark.unit
def test_the_exec_context_carries_the_measurements_positional_args():
    """A narrowed Mutant strips the run's positional path, so the exec context must carry the Measurement's."""
    from types import SimpleNamespace

    from mutate4py._runner import SelectionOutcome, _mutant_exec_ctx

    request = SimpleNamespace(path="calc.py", cwd="/proj", pytest_args=["-k", "tests", "tests"], forking_requested=True)
    outcome = SelectionOutcome(
        mutant_pytest_args=["-k", "tests", "tests"],
        measurement=SimpleNamespace(positional_args=("tests",)),
    )

    ctx = _mutant_exec_ctx(request, outcome, test_ctx_db=None)

    assert ctx.positionals == ("tests",)


@pytest.mark.unit
def test_the_timeout_policy_budgets_the_full_set_as_all_and_adds_the_measured_overhead(tmp_path):
    """The full test set is budgeted as the Measurement's ALL; the Per-Mutant overhead is added to the timeout."""
    from types import SimpleNamespace

    from mutate4py._measurement import ALL
    from mutate4py._runner import _prepare_baseline_and_executor

    budgeted = []

    def budget_of(node_ids):
        budgeted.append(node_ids)
        return 2.0

    measurement = SimpleNamespace(wall=10.0, per_mutant_overhead=0.5, budget_of=budget_of)
    request = SimpleNamespace(
        timeout_factor=3.0,
        min_timeout=1.0,
        forking_requested=False,
        executor=None,
        cwd=str(tmp_path),
        path=str(tmp_path / "calc.py"),
    )
    setup = SimpleNamespace(bak_path=str(tmp_path / "calc.py.bak"), loaded=SimpleNamespace(clean_source="x = 1\n"))

    policy = _prepare_baseline_and_executor(request, setup, measurement, [], use_parallel=False).timeout_policy

    # max(1.0, 3.0 x 2.0) + 0.5 for both the full set and one Mutant's own tests.
    assert policy.timeout_for(None) == 6.5
    assert policy.timeout_for(frozenset({"tests/test_calc.py::test_gt"})) == 6.5
    assert budgeted == [ALL, frozenset({"tests/test_calc.py::test_gt"})]


@pytest.mark.unit
def test_a_run_with_no_selection_tally_prints_the_report_without_a_selection_line(caplog):
    """A run whose selection was never tallied prints the Mutation Report with no Test selection line."""
    import logging
    from types import SimpleNamespace

    from mutate4py._runner import _report_run

    request = SimpleNamespace(measurement=None, test_contexts_path=None, allow_survivors=False)
    outcome = SimpleNamespace(overhead_duration=None, baseline_duration=0.0, uncovered_count=0, measurement=None)
    result = SimpleNamespace(counts={"killed": 1, "timeout": 0, "survived": 0}, selection_counts=None)
    scored_run = SimpleNamespace(unaccepted=lambda: [], accepted=lambda: [])

    with caplog.at_level(logging.INFO, logger="mutate4py._runner"):
        code = _report_run(request, outcome, result, scored_run)

    assert code == 0
    assert "Mutation Report" in caplog.text
    assert "Test selection:" not in caplog.text


@pytest.mark.unit
def test_a_run_that_measured_its_own_baseline_prints_its_measurement_line(caplog):
    """A run not handed a Measurement prints the Measurement line it measured itself."""
    import logging
    from types import SimpleNamespace

    from mutate4py._runner import _report_run

    measurement = SimpleNamespace(wall=1.5, tests=3, core="sysmon", note=None)
    request = SimpleNamespace(measurement=None, test_contexts_path=None, allow_survivors=False)
    outcome = SimpleNamespace(overhead_duration=0.25, baseline_duration=2.0, uncovered_count=0, measurement=measurement)
    result = SimpleNamespace(counts={"killed": 1, "timeout": 0, "survived": 0}, selection_counts=None)
    scored_run = SimpleNamespace(unaccepted=lambda: [], accepted=lambda: [])

    with caplog.at_level(logging.INFO, logger="mutate4py._runner"):
        _report_run(request, outcome, result, scored_run)

    assert "Measurement: 1.50s, 3 tests, core sysmon" in caplog.text
