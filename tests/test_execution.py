"""Unit tests for the mutant execution engine (_execution.py)."""

import subprocess

import pytest

from mutate4py._discovery import apply_mutant, discover_sites
from mutate4py._execution import (
    MutantExecCtx,
    NoTestsCollectedError,
    _confirm_survivors,
    _execute_mutations,
    _run_mutation_loop,
    _run_parallel_workers,
)
from mutate4py._executor import ExecutorDescription, MutantTiming
from mutate4py._subprocess_executor import SubprocessExecutor
from mutate4py._test_dispatch import TimeoutPolicy
from mutate4py._workers import ParallelRunResult

from ._scripted_executor import ScriptedExecutor


class _FakeExecutor:
    def __init__(self, status="survived"):
        self._status = status
        self.calls = []

    def prime(self):
        pass

    def run(self, args, timeout):
        self.calls.append((list(args), timeout))
        return self._status

    def describe(self):
        return ExecutorDescription(mode="subprocess", reason="--no-fork")


def _parallel_result(counts, survivors=()):
    """What run_parallel hands back for a run whose Workers all ran unforked."""
    return ParallelRunResult(
        counts=counts,
        survivors=list(survivors),
        selection_counts=None,
        timing=MutantTiming(),
        executor_description=ExecutorDescription(mode="subprocess", reason="--no-fork"),
    )


def _policy(timeout: float) -> TimeoutPolicy:
    """A TimeoutPolicy whose floor is `timeout`, so the Mutant timeout comes out exactly `timeout`."""
    return TimeoutPolicy(factor=1.0, min_timeout=timeout, overhead=0.0, budget_of=lambda node_ids: 0.0)


class _FakeSelectionSource:
    def __init__(self, outcome, node_ids=()):
        self._result = (outcome, list(node_ids))

    def tests_for_line(self, source_path, line):
        return self._result


# ── _run_mutation_loop ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_run_mutation_loop_empty_sites_returns_zero_counts(tmp_path):
    """Zero selected sites means all counts start and stay at zero — kills initial-value mutants."""
    src_file = tmp_path / "calc.py"
    src_file.write_text("x = 1\n")
    counts, survivors, selection_counts = _run_mutation_loop(
        selected_sites=[],
        clean_source="x = 1\n",
        ctx=MutantExecCtx(
            path=str(src_file),
            cwd=str(tmp_path),
            pytest_args=[],
            executor=_FakeExecutor(),
            timeout_policy=_policy(5.0),
        ),
    )
    assert counts == {"killed": 0, "timeout": 0, "survived": 0}
    assert survivors == []
    assert selection_counts is None


def _loop_over_two_sites(tmp_path, selection_source):
    src = "def f(a, b):\n    return a > b\n\n\ndef g(a, b):\n    return a + b\n"
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_calc.py").write_text("")
    return _run_mutation_loop(
        selected_sites=discover_sites(src),
        clean_source=src,
        ctx=MutantExecCtx(
            path=str(src_file),
            cwd=str(tmp_path),
            pytest_args=[],
            executor=_FakeExecutor(status="killed"),
            timeout_policy=_policy(5.0),
            selection_source=selection_source,
            abs_source_path=str(src_file),
        ),
    )


@pytest.mark.unit
def test_run_mutation_loop_tallies_narrowed_selections(tmp_path):
    _, _, selection_counts = _loop_over_two_sites(
        tmp_path, _FakeSelectionSource("narrowed", ["tests/test_calc.py::test_f"])
    )
    assert selection_counts == {"narrowed": 2, "static": 0}


@pytest.mark.unit
@pytest.mark.parametrize("outcome", ["static", "uncovered"])
def test_run_mutation_loop_tallies_static_selections(tmp_path, outcome):
    """A line no test owns (static) and a line no test reached (uncovered) both run the full set, tallied static."""
    _, _, selection_counts = _loop_over_two_sites(tmp_path, _FakeSelectionSource(outcome))
    assert selection_counts == {"narrowed": 0, "static": 2}


@pytest.mark.unit
def test_run_mutation_loop_calls_executor_with_planned_args_and_timeout(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    executor = _FakeExecutor(status="survived")

    counts, survivors, _ = _run_mutation_loop(
        selected_sites=discover_sites(src),
        clean_source=src,
        ctx=MutantExecCtx(
            path=str(src_file),
            cwd=str(tmp_path),
            pytest_args=["-q"],
            executor=executor,
            timeout_policy=_policy(7.5),
        ),
    )
    assert counts == {"killed": 0, "timeout": 0, "survived": 1}
    assert survivors == discover_sites(src)
    assert executor.calls == [(["-q"], 7.5)]


@pytest.mark.unit
def test_run_mutation_loop_unrecognized_selection_outcome_aborts_before_applying_the_mutant(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    with pytest.raises(ValueError, match="unrecognized selection outcome"):
        _run_mutation_loop(
            selected_sites=discover_sites(src),
            clean_source=src,
            ctx=MutantExecCtx(
                path=str(src_file),
                cwd=str(tmp_path),
                pytest_args=[],
                executor=_FakeExecutor(),
                timeout_policy=_policy(5.0),
                selection_source=_FakeSelectionSource("bogus"),
                abs_source_path=str(src_file),
            ),
        )
    assert src_file.read_text() == src


@pytest.mark.unit
@pytest.mark.parametrize(
    "status, hint",
    [
        ("no-tests-collected", "pytest collected no tests"),
        ("usage-error", "usage error before collecting any test"),
    ],
)
def test_run_mutation_loop_no_tests_collected_raises(tmp_path, status, hint):
    """A Mutant whose test run exercised no test at all must abort, not be
    tallied `killed` (issue #55)."""
    src = "def f(a, b):\n    return a > b\n"
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    with pytest.raises(NoTestsCollectedError) as excinfo:
        _run_mutation_loop(
            selected_sites=discover_sites(src),
            clean_source=src,
            ctx=MutantExecCtx(
                path=str(src_file),
                cwd=str(tmp_path),
                pytest_args=[],
                executor=_FakeExecutor(status=status),
                timeout_policy=_policy(5.0),
                abs_source_path=str(src_file),
            ),
        )
    message = str(excinfo.value)
    assert f"{src_file}:2" in message
    assert hint in message


class _StepClock:
    """Stands in for the time module: each monotonic() call returns the next scripted reading."""

    def __init__(self, readings):
        self._readings = iter(readings)

    def monotonic(self):
        return next(self._readings)


@pytest.mark.unit
def test_run_mutation_loop_times_a_killed_mutant_into_the_mutants_bucket(tmp_path, monkeypatch):
    import mutate4py._execution as execution_mod

    src = "def f(a, b):\n    return a > b\n"
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    monkeypatch.setattr(execution_mod, "time", _StepClock([10.0, 11.5]))
    ctx = MutantExecCtx(
        path=str(src_file),
        cwd=str(tmp_path),
        pytest_args=[],
        executor=_FakeExecutor(status="killed"),
        timeout_policy=_policy(5.0),
    )

    _run_mutation_loop(selected_sites=discover_sites(src), clean_source=src, ctx=ctx)

    assert (ctx.timing.mutants_count, ctx.timing.mutants_seconds) == (1, 1.5)
    assert (ctx.timing.timeouts_count, ctx.timing.timeouts_seconds) == (0, 0.0)


@pytest.mark.unit
def test_run_mutation_loop_times_a_timed_out_mutant_into_the_timeouts_bucket(tmp_path, monkeypatch):
    import mutate4py._execution as execution_mod

    src = "def f(a, b):\n    return a > b\n"
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    monkeypatch.setattr(execution_mod, "time", _StepClock([0.0, 3.0]))
    ctx = MutantExecCtx(
        path=str(src_file),
        cwd=str(tmp_path),
        pytest_args=[],
        executor=_FakeExecutor(status="timeout"),
        timeout_policy=_policy(5.0),
    )

    _run_mutation_loop(selected_sites=discover_sites(src), clean_source=src, ctx=ctx)

    assert (ctx.timing.timeouts_count, ctx.timing.timeouts_seconds) == (1, 3.0)
    assert (ctx.timing.mutants_count, ctx.timing.mutants_seconds) == (0, 0.0)


# ── _run_mutation_loop: a Mutant that ends in pytest exit 4 or 5 ─────────────────


_ONE_SITE = "def f(a, b):\n    return a > b\n"


def _loop_ctx(tmp_path, statuses, source=_ONE_SITE, **extra):
    src_file = tmp_path / "calc.py"
    src_file.write_text(source)
    executor = ScriptedExecutor(str(src_file), statuses)
    ctx = MutantExecCtx(
        path=str(src_file),
        cwd=str(tmp_path),
        pytest_args=["-q"],
        executor=executor,
        timeout_policy=_policy(5.0),
        abs_source_path=str(src_file),
        **extra,
    )
    return ctx, executor


@pytest.mark.unit
@pytest.mark.parametrize("status", ["usage-error", "no-tests-collected"])
def test_run_mutation_loop_kills_a_mutant_that_breaks_the_run_when_the_original_code_runs_tests(
    tmp_path, monkeypatch, status
):
    """A Mutant that breaks the module at import fails the conftest import, so pytest exits 4 before
    any test. The same argv on the original code runs tests: the Mutant caused the exit, and it is killed."""
    import mutate4py._execution as execution_mod

    # Two readings for the one Mutant. A timed control run would need two more and end the clock.
    monkeypatch.setattr(execution_mod, "time", _StepClock([10.0, 11.5]))
    ctx, executor = _loop_ctx(tmp_path, [status, "survived"])
    site = discover_sites(_ONE_SITE)[0]

    counts, survivors, _ = _run_mutation_loop(selected_sites=[site], clean_source=_ONE_SITE, ctx=ctx)

    assert counts == {"killed": 1, "timeout": 0, "survived": 0}
    assert survivors == []
    assert executor.calls == [(["-q"], 5.0), (["-q"], 5.0)]
    assert executor.seen_sources == [apply_mutant(_ONE_SITE, site), _ONE_SITE]
    assert (ctx.timing.mutants_count, ctx.timing.mutants_seconds) == (1, 1.5)


@pytest.mark.unit
@pytest.mark.parametrize("control", ["usage-error", "no-tests-collected", "timeout", "errored"])
def test_run_mutation_loop_aborts_when_the_control_run_on_the_original_code_runs_no_test(tmp_path, control):
    """The original code gives the same exit, or no answer (a timeout; an exit 2 or 3, a signal, a pytest that
    did not start): the argv may be the defect, so the run aborts."""
    ctx, _ = _loop_ctx(tmp_path, ["usage-error", control])

    with pytest.raises(NoTestsCollectedError, match="usage error before collecting any test"):
        _run_mutation_loop(selected_sites=discover_sites(_ONE_SITE), clean_source=_ONE_SITE, ctx=ctx)


@pytest.mark.unit
def test_run_mutation_loop_aborts_when_pytest_cannot_start_for_the_control_run(tmp_path, monkeypatch):
    """The Mutant's pytest exits 4 on a bad argv. The Control run then fails to start (the OS refuses the
    process): that is no proof the argv runs tests, so the run aborts and no kill is scored."""
    outcomes = iter([subprocess.CompletedProcess([], 4), OSError("cannot start")])

    def fake_run(argv, **kwargs):
        outcome = next(outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(subprocess, "run", fake_run)
    src_file = tmp_path / "calc.py"
    src_file.write_text(_ONE_SITE)
    ctx = MutantExecCtx(
        path=str(src_file),
        cwd=str(tmp_path),
        pytest_args=["--no-such-flag"],
        executor=SubprocessExecutor(str(tmp_path), str(src_file)),
        timeout_policy=_policy(5.0),
        abs_source_path=str(src_file),
    )

    with pytest.raises(NoTestsCollectedError, match="usage error before collecting any test"):
        _run_mutation_loop(selected_sites=discover_sites(_ONE_SITE), clean_source=_ONE_SITE, ctx=ctx)


@pytest.mark.unit
def test_run_mutation_loop_tallies_a_mutant_that_ends_abnormally_as_killed_with_no_control_run(tmp_path):
    ctx, executor = _loop_ctx(tmp_path, ["errored"])

    counts, survivors, _ = _run_mutation_loop(selected_sites=discover_sites(_ONE_SITE), clean_source=_ONE_SITE, ctx=ctx)

    assert counts == {"killed": 1, "timeout": 0, "survived": 0}
    assert survivors == []
    assert len(executor.calls) == 1


@pytest.mark.unit
def test_run_mutation_loop_runs_one_control_for_every_mutant_that_runs_the_same_argv(tmp_path):
    two_sites = "def f(a, b):\n    return a > b\n\n\ndef g(a, b):\n    return a + b\n"
    ctx, executor = _loop_ctx(tmp_path, ["no-tests-collected", "survived", "usage-error"], source=two_sites)

    counts, _, _ = _run_mutation_loop(selected_sites=discover_sites(two_sites), clean_source=two_sites, ctx=ctx)

    assert counts["killed"] == 2
    assert len(executor.calls) == 3


@pytest.mark.unit
def test_run_mutation_loop_aborts_before_applying_the_mutant_when_a_node_id_file_is_missing(tmp_path):
    """Pytest exits 4 on a node id whose file is not under the run directory. The plan says so before
    any Mutant runs, so the result never depends on how the Mutant timeout compares with pytest start-up."""
    ctx, executor = _loop_ctx(
        tmp_path, [], selection_source=_FakeSelectionSource("narrowed", ["tests/test_gone.py::t"])
    )

    with pytest.raises(NoTestsCollectedError, match="tests/test_gone.py::t"):
        _run_mutation_loop(selected_sites=discover_sites(_ONE_SITE), clean_source=_ONE_SITE, ctx=ctx)

    assert executor.calls == []
    assert (tmp_path / "calc.py").read_text() == _ONE_SITE


# ── _run_parallel_workers passes timeout_policy ───────────────────────────────


@pytest.mark.unit
def test_run_parallel_workers_passes_timeout(tmp_path, monkeypatch):
    """timeout_policy is forwarded to run_parallel (not silently replaced with None)."""
    import mutate4py._workers as workers_mod

    captured = {}

    def fake_run_parallel(request):
        captured["timeout_policy"] = request.timeout_policy
        return _parallel_result({"killed": 0, "survived": 0, "timeout": 0})

    monkeypatch.setattr(workers_mod, "run_parallel", fake_run_parallel)
    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root, required: None)

    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "f.py")
    with open(src_path, "w") as f:
        f.write(src)

    sites = discover_sites(src)

    _run_parallel_workers(
        selected_sites=sites,
        clean_source=src,
        ctx=MutantExecCtx(
            path=src_path,
            cwd=str(tmp_path),
            pytest_args=[],
            executor=_FakeExecutor(),
            timeout_policy=_policy(42.0),
            max_workers=2,
        ),
    )
    assert captured["timeout_policy"].timeout_for(None) == 42.0


# ── _confirm_survivors ────────────────────────────────────────────────────────

FULL_SET = ["-q", "tests"]


class _SourceRecordingExecutor(_FakeExecutor):
    """A fake executor that also records the source text on disk when each run starts."""

    def __init__(self, path, status):
        super().__init__(status=status)
        self._path = path
        self.seen_sources = []

    def run(self, args, timeout):
        with open(self._path) as f:
            self.seen_sources.append(f.read())
        return super().run(args, timeout)


def _confirm_ctx(tmp_path, src_file, markers=None) -> MutantExecCtx:
    return MutantExecCtx(
        path=str(src_file),
        cwd=str(tmp_path),
        pytest_args=["-q"],
        executor=_FakeExecutor(),
        timeout_policy=_policy(7.5),
        abs_source_path=str(src_file),
        confirm_args=list(FULL_SET),
        markers=markers or {},
    )


@pytest.mark.unit
def test_confirm_survivors_a_full_set_kill_removes_the_survivor(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    site = discover_sites(src)[0]
    executor = _SourceRecordingExecutor(str(src_file), status="killed")

    still, runs, kills = _confirm_survivors([site], src, _confirm_ctx(tmp_path, src_file), executor)

    assert still == []
    assert (runs, kills) == (1, 1)
    assert executor.calls == [(FULL_SET, 7.5)]
    assert executor.seen_sources == [apply_mutant(src, site)]


@pytest.mark.unit
def test_confirm_survivors_times_each_confirmation_run_into_the_timing(tmp_path, monkeypatch):
    import mutate4py._execution as execution_mod

    src = "def f(a, b):\n    return a > b\n"
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    site = discover_sites(src)[0]
    monkeypatch.setattr(execution_mod, "time", _StepClock([10.0, 12.0]))
    ctx = _confirm_ctx(tmp_path, src_file)

    _confirm_survivors([site], src, ctx, _FakeExecutor(status="timeout"))

    assert (ctx.timing.confirmation_runs, ctx.timing.confirmation_kills, ctx.timing.confirmation_seconds) == (1, 1, 2.0)


@pytest.mark.unit
def test_confirm_survivors_a_timeout_under_the_full_set_is_folded_into_a_kill(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    site = discover_sites(src)[0]

    still, runs, kills = _confirm_survivors(
        [site], src, _confirm_ctx(tmp_path, src_file), _FakeExecutor(status="timeout")
    )

    assert (still, runs, kills) == ([], 1, 1)


@pytest.mark.unit
def test_confirm_survivors_a_survivor_the_full_set_also_lets_through_stays_a_survivor(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    site = discover_sites(src)[0]

    still, runs, kills = _confirm_survivors(
        [site], src, _confirm_ctx(tmp_path, src_file), _FakeExecutor(status="survived")
    )

    assert (still, runs, kills) == ([site], 1, 0)


@pytest.mark.unit
def test_confirm_survivors_an_accepted_equivalent_survivor_is_not_confirmed(tmp_path):
    """A Survivor on a marker line stays accepted and is never re-run; the unmarked one is confirmed."""
    src = "def f(a, b):\n    return a > b\n\n\ndef g(a, b):\n    return a + b\n"
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    sites = discover_sites(src)
    marked = next(s for s in sites if s.line == 2)
    plain = next(s for s in sites if s.line == 6)
    executor = _SourceRecordingExecutor(str(src_file), status="killed")

    still, runs, kills = _confirm_survivors(
        [marked, plain], src, _confirm_ctx(tmp_path, src_file, markers={2: "equivalent"}), executor
    )

    assert (still, runs, kills) == ([marked], 1, 1)
    assert executor.seen_sources == [apply_mutant(src, plain)]


@pytest.mark.unit
def test_confirm_survivors_a_full_set_run_that_breaks_pytest_is_a_kill_when_the_original_code_runs_tests(tmp_path):
    src_file = tmp_path / "calc.py"
    src_file.write_text(_ONE_SITE)
    site = discover_sites(_ONE_SITE)[0]
    executor = ScriptedExecutor(str(src_file), ["usage-error", "survived"])

    still, runs, kills = _confirm_survivors([site], _ONE_SITE, _confirm_ctx(tmp_path, src_file), executor)

    assert (still, runs, kills) == ([], 1, 1)
    assert executor.calls == [(FULL_SET, 7.5), (FULL_SET, 7.5)]
    assert executor.seen_sources == [apply_mutant(_ONE_SITE, site), _ONE_SITE]


@pytest.mark.unit
def test_confirm_survivors_a_full_set_run_that_ends_abnormally_is_a_kill(tmp_path):
    src_file = tmp_path / "calc.py"
    src_file.write_text(_ONE_SITE)
    site = discover_sites(_ONE_SITE)[0]
    executor = ScriptedExecutor(str(src_file), ["errored"])

    still, runs, kills = _confirm_survivors([site], _ONE_SITE, _confirm_ctx(tmp_path, src_file), executor)

    assert (still, runs, kills) == ([], 1, 1)
    assert len(executor.calls) == 1


@pytest.mark.unit
def test_confirm_survivors_aborts_when_the_control_run_on_the_original_code_runs_no_test(tmp_path):
    src_file = tmp_path / "calc.py"
    src_file.write_text(_ONE_SITE)
    site = discover_sites(_ONE_SITE)[0]
    executor = ScriptedExecutor(str(src_file), ["no-tests-collected", "no-tests-collected"])

    with pytest.raises(NoTestsCollectedError, match="collected no tests"):
        _confirm_survivors([site], _ONE_SITE, _confirm_ctx(tmp_path, src_file), executor)


@pytest.mark.unit
def test_parallel_survivors_are_confirmed_by_the_orchestrator_as_the_serial_loop_confirms_them(tmp_path, monkeypatch):
    """The Workers return their Survivors; the orchestrator re-runs each with the full set in a subprocess executor."""
    import mutate4py._execution as execution_mod
    import mutate4py._workers as workers_mod

    src = "def f(a, b):\n    return a > b\n"
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    sites = discover_sites(src)
    monkeypatch.setattr(
        workers_mod,
        "run_parallel",
        lambda request: _parallel_result({"killed": 0, "timeout": 0, "survived": 1}, survivors=sites),
    )
    confirm = _SourceRecordingExecutor(str(src_file), status="killed")
    monkeypatch.setattr(execution_mod, "SubprocessExecutor", lambda cwd, guarded_path: confirm)

    outcome = _execute_mutations(
        selected_sites=sites,
        clean_source=src,
        ctx=MutantExecCtx(
            path=str(src_file),
            cwd=str(tmp_path),
            pytest_args=["-q"],
            executor=_FakeExecutor(),
            timeout_policy=_policy(7.5),
            max_workers=2,
            use_parallel=True,
            abs_source_path=str(src_file),
            confirm_args=list(FULL_SET),
        ),
    )

    assert outcome.survivors == []
    assert outcome.counts == {"killed": 1, "timeout": 0, "survived": 0}
    assert (outcome.confirmation_runs, outcome.confirmation_kills) == (1, 1)
    assert confirm.calls == [(FULL_SET, 7.5)]


@pytest.mark.unit
def test_parallel_outcome_carries_the_workers_description_and_their_mutants_timing(tmp_path, monkeypatch):
    """The Executor and Time lines of a parallel run come from what its Workers reported, not the orchestrator's."""
    import mutate4py._execution as execution_mod
    import mutate4py._workers as workers_mod

    src = "def f(a, b):\n    return a > b\n"
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    worker_timing = MutantTiming()
    worker_timing.record("killed", 2.0)
    monkeypatch.setattr(
        workers_mod,
        "run_parallel",
        lambda request: ParallelRunResult(
            counts={"killed": 1, "timeout": 0, "survived": 0},
            survivors=[],
            selection_counts=None,
            timing=worker_timing,
            executor_description=ExecutorDescription(mode="forking", fresh_import=3),
        ),
    )
    monkeypatch.setattr(execution_mod, "SubprocessExecutor", lambda cwd, guarded_path: _FakeExecutor())

    outcome = _execute_mutations(
        selected_sites=discover_sites(src),
        clean_source=src,
        ctx=MutantExecCtx(
            path=str(src_file),
            cwd=str(tmp_path),
            pytest_args=["-q"],
            executor=None,
            timeout_policy=_policy(7.5),
            max_workers=2,
            use_parallel=True,
            abs_source_path=str(src_file),
            confirm_args=list(FULL_SET),
        ),
    )

    assert outcome.executor_description == ExecutorDescription(mode="forking", fresh_import=3)
    assert (outcome.timing.mutants_count, outcome.timing.mutants_seconds) == (1, 2.0)
