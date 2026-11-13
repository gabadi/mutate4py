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
        measurement=SimpleNamespace(positional_args=("tests",), empty_lines=lambda path: frozenset()),
    )

    ctx = _mutant_exec_ctx(request, outcome)

    assert ctx.positionals == ("tests",)


@pytest.mark.unit
def test_the_exec_context_carries_the_guarded_files_lines_that_ran_at_import(tmp_path):
    """Swap mode refuses a changed body the Measurement saw run under the Empty context."""
    from types import SimpleNamespace

    from mutate4py._runner import SelectionOutcome, _mutant_exec_ctx

    target = str(tmp_path / "calc.py")
    request = SimpleNamespace(path=target, cwd=str(tmp_path), pytest_args=[], forking_requested=True)
    empty = {target: frozenset({3, 7})}
    outcome = SelectionOutcome(
        mutant_pytest_args=[],
        measurement=SimpleNamespace(positional_args=(), empty_lines=lambda path: empty.get(path, frozenset())),
    )

    assert _mutant_exec_ctx(request, outcome).ran_at_import == frozenset({3, 7})


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

    measurement = SimpleNamespace(
        wall=10.0, per_mutant_overhead=0.5, budget_of=budget_of, empty_lines=lambda path: frozenset()
    )
    request = SimpleNamespace(
        timeout_factor=3.0,
        min_timeout=1.0,
        forking_requested=False,
        executor=None,
        cwd=str(tmp_path),
        path=str(tmp_path / "calc.py"),
        pytest_args=[],
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

    from mutate4py._executor import ExecutorDescription, MutantTiming
    from mutate4py._runner import _report_run

    request = SimpleNamespace(measurement=None, timing_sink=None, allow_survivors=False)
    outcome = SimpleNamespace(overhead_duration=None, baseline_duration=0.0, uncovered_count=0, measurement=None)
    result = SimpleNamespace(
        counts={"killed": 1, "timeout": 0, "survived": 0},
        selection_counts=None,
        timing=MutantTiming(),
        executor_description=ExecutorDescription(mode="subprocess", reason="--no-fork"),
    )
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

    from mutate4py._executor import ExecutorDescription, MutantTiming
    from mutate4py._runner import _report_run

    measurement = SimpleNamespace(wall=1.5, tests=3, core="sysmon", note=None)
    request = SimpleNamespace(measurement=None, timing_sink=None, allow_survivors=False)
    outcome = SimpleNamespace(overhead_duration=0.25, baseline_duration=2.0, uncovered_count=0, measurement=measurement)
    result = SimpleNamespace(
        counts={"killed": 1, "timeout": 0, "survived": 0},
        selection_counts=None,
        timing=MutantTiming(),
        executor_description=ExecutorDescription(mode="subprocess", reason="--no-fork"),
    )
    scored_run = SimpleNamespace(unaccepted=lambda: [], accepted=lambda: [])

    with caplog.at_level(logging.INFO, logger="mutate4py._runner"):
        _report_run(request, outcome, result, scored_run)

    assert "Measurement: 1.50s, 3 tests, core sysmon" in caplog.text


@pytest.mark.unit
def test_a_run_with_no_selected_mutants_names_that_as_the_subprocess_executor_reason(tmp_path):
    """A run that asked for forking but selected nothing prepares the subprocess executor and says why."""
    from types import SimpleNamespace

    from mutate4py._runner import _prepare_baseline_and_executor

    measurement = SimpleNamespace(
        wall=1.0, per_mutant_overhead=0.0, budget_of=lambda node_ids: 1.0, empty_lines=lambda path: frozenset()
    )
    request = SimpleNamespace(
        timeout_factor=3.0,
        min_timeout=1.0,
        forking_requested=True,
        executor=None,
        cwd=str(tmp_path),
        path=str(tmp_path / "calc.py"),
        pytest_args=[],
    )
    setup = SimpleNamespace(bak_path=str(tmp_path / "calc.py.bak"), loaded=SimpleNamespace(clean_source="x = 1\n"))

    executor = _prepare_baseline_and_executor(request, setup, measurement, [], use_parallel=False).executor

    assert executor.describe().render() == "subprocess (no Mutants selected)"


@pytest.mark.unit
def test_a_no_fork_run_names_no_fork_as_the_reason_even_when_nothing_is_selected(tmp_path):
    """The user's --no-fork is the reason reported, ahead of the no-Mutants reason."""
    from types import SimpleNamespace

    from mutate4py._runner import _prepare_baseline_and_executor

    measurement = SimpleNamespace(
        wall=1.0, per_mutant_overhead=0.0, budget_of=lambda node_ids: 1.0, empty_lines=lambda path: frozenset()
    )
    request = SimpleNamespace(
        timeout_factor=3.0,
        min_timeout=1.0,
        forking_requested=False,
        executor=None,
        cwd=str(tmp_path),
        path=str(tmp_path / "calc.py"),
        pytest_args=[],
    )
    setup = SimpleNamespace(bak_path=str(tmp_path / "calc.py.bak"), loaded=SimpleNamespace(clean_source="x = 1\n"))

    executor = _prepare_baseline_and_executor(request, setup, measurement, [], use_parallel=False).executor

    assert executor.describe().render() == "subprocess (--no-fork)"


@pytest.mark.unit
def test_a_run_report_prints_its_time_and_executor_lines_between_the_mutation_report_and_the_measurement(caplog):
    """The Time and Executor lines close the Mutation Report, ahead of the Measurement lines."""
    import logging
    from types import SimpleNamespace

    from mutate4py._executor import ExecutorDescription, MutantTiming
    from mutate4py._runner import _report_run

    measurement = SimpleNamespace(wall=1.5, tests=3, core="sysmon", note=None)
    request = SimpleNamespace(measurement=None, timing_sink=None, allow_survivors=False)
    outcome = SimpleNamespace(overhead_duration=0.25, baseline_duration=2.0, uncovered_count=0, measurement=measurement)
    result = SimpleNamespace(
        counts={"killed": 2, "timeout": 0, "survived": 0},
        selection_counts=None,
        timing=MutantTiming(mutants_seconds=1.5, mutants_count=2),
        executor_description=ExecutorDescription(mode="subprocess", reason="--no-fork"),
    )
    scored_run = SimpleNamespace(unaccepted=lambda: [], accepted=lambda: [])

    with caplog.at_level(logging.INFO, logger="mutate4py._runner"):
        _report_run(request, outcome, result, scored_run)

    text = caplog.text
    report_at = text.index("Mutation Report")
    time_at = text.index("Time: mutants 1.50s (2)")
    executor_at = text.index("Executor: subprocess (--no-fork)")
    measurement_at = text.index("Measurement: 1.50s")
    assert report_at < time_at < executor_at < measurement_at


class _CallerOwnedExecutor:
    """Stands in for an executor the caller already owns and primed: any use here fails the test."""

    def prime(self):  # pragma: no cover - the run must never re-prime it
        raise AssertionError("a caller-supplied executor must not be re-primed")

    def run(self, args, timeout):  # pragma: no cover - never dispatched here
        raise AssertionError("must not dispatch")

    def describe(self):  # pragma: no cover - never described here
        raise AssertionError("must not describe")


@pytest.mark.unit
@pytest.mark.parametrize("use_parallel", [False, True])
def test_a_caller_supplied_executor_is_used_unprimed_serial_or_parallel(tmp_path, use_parallel):
    from types import SimpleNamespace

    from mutate4py._runner import _prepare_baseline_and_executor

    supplied = _CallerOwnedExecutor()
    measurement = SimpleNamespace(
        wall=1.0, per_mutant_overhead=0.0, budget_of=lambda node_ids: 1.0, empty_lines=lambda path: frozenset()
    )
    request = SimpleNamespace(
        timeout_factor=3.0,
        min_timeout=1.0,
        forking_requested=True,
        executor=supplied,
        cwd=str(tmp_path),
        path=str(tmp_path / "calc.py"),
        pytest_args=[],
    )
    setup = SimpleNamespace(bak_path=str(tmp_path / "calc.py.bak"), loaded=SimpleNamespace(clean_source="x = 1\n"))

    prep = _prepare_baseline_and_executor(request, setup, measurement, ["a site"], use_parallel=use_parallel)

    assert prep.executor is supplied


@pytest.mark.unit
def test_a_parallel_run_selects_no_executor_and_leaves_priming_to_each_worker(tmp_path, monkeypatch):
    """None, not a prepared executor: a parallel run primes one Executor per
    Worker in that Worker's own process (issue 04b)."""
    from types import SimpleNamespace

    from mutate4py._runner import _prepare_baseline_and_executor

    monkeypatch.setattr("mutate4py._runner.select_executor", lambda **kwargs: pytest.fail("must not select"))
    measurement = SimpleNamespace(
        wall=1.0, per_mutant_overhead=0.0, budget_of=lambda node_ids: 1.0, empty_lines=lambda path: frozenset()
    )
    request = SimpleNamespace(
        timeout_factor=3.0,
        min_timeout=1.0,
        forking_requested=True,
        executor=None,
        cwd=str(tmp_path),
        path=str(tmp_path / "calc.py"),
        pytest_args=[],
    )
    setup = SimpleNamespace(bak_path=str(tmp_path / "calc.py.bak"), loaded=SimpleNamespace(clean_source="x = 1\n"))

    assert _prepare_baseline_and_executor(request, setup, measurement, ["a site"], use_parallel=True).executor is None
