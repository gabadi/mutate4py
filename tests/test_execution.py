"""Unit tests for the mutant execution engine (_execution.py)."""

import pytest

from mutate4py._discovery import discover_sites
from mutate4py._execution import (
    MutantExecCtx,
    NoTestsCollectedError,
    TestSelectionError,
    _build_mutant_args,
    _run_mutation_loop,
    _run_parallel_workers,
)


class _FakeExecutor:
    def __init__(self, status="survived"):
        self._status = status
        self.calls = []

    def prime(self):
        pass

    def run(self, args, timeout):
        self.calls.append((list(args), timeout))
        return self._status


# ── _build_mutant_args ───────────────────────────────────────────────────────


class _FakeTestContextDB:
    def __init__(self, outcome, node_ids=()):
        self._result = (outcome, list(node_ids))

    def tests_for_line(self, source_path, line):
        return self._result


def _one_site(src="def f(a, b):\n    return a > b\n"):
    return discover_sites(src)[0]


@pytest.mark.unit
def test_build_mutant_args_no_ctx_db_returns_full_args():
    assert _build_mutant_args(["-q"], None, "/src/calc.py", _one_site()) == (["-q"], None)


@pytest.mark.unit
def test_build_mutant_args_narrows_to_covering_tests():
    ctx_db = _FakeTestContextDB("narrowed", ["tests/test_calc.py::test_gt"])
    assert _build_mutant_args(["-q"], ctx_db, "/src/calc.py", _one_site()) == (
        ["-q", "tests/test_calc.py::test_gt"],
        "narrowed",
    )


@pytest.mark.unit
def test_build_mutant_args_static_line_runs_full_args():
    ctx_db = _FakeTestContextDB("static")
    assert _build_mutant_args(["-q"], ctx_db, "/src/calc.py", _one_site()) == (["-q"], "static")


@pytest.mark.unit
def test_build_mutant_args_under_listed_runs_full_args_tallied_as_degraded():
    """An under-listed line (issue #69) degrades to a full-suite run, same
    dispatch as "static", but tallied separately so the report can name it."""
    ctx_db = _FakeTestContextDB("under-listed", ["tests/test_calc.py::test_gt"])
    assert _build_mutant_args(["-q"], ctx_db, "/src/calc.py", _one_site()) == (["-q"], "degraded")


@pytest.mark.unit
@pytest.mark.parametrize(
    "outcome, hint",
    [
        ("line-absent", "absent from the test-context db"),
        ("file-absent", "not in the test-context db"),
    ],
)
def test_build_mutant_args_disagreement_raises(outcome, hint):
    ctx_db = _FakeTestContextDB(outcome)
    with pytest.raises(TestSelectionError) as excinfo:
        _build_mutant_args([], ctx_db, "/src/calc.py", _one_site())
    message = str(excinfo.value)
    assert "/src/calc.py:2" in message
    assert hint in message


@pytest.mark.unit
def test_build_mutant_args_unrecognized_outcome_raises():
    """No outcome may fall through to a full-suite run counted as narrowed."""
    ctx_db = _FakeTestContextDB("something-new")
    with pytest.raises(TestSelectionError, match="unrecognized selection outcome"):
        _build_mutant_args([], ctx_db, "/src/calc.py", _one_site())


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
            mutant_timeout=5.0,
        ),
    )
    assert counts == {"killed": 0, "timeout": 0, "survived": 0}
    assert survivors == []
    assert selection_counts is None


def _loop_over_two_sites(tmp_path, ctx_db):
    src = "def f(a, b):\n    return a > b\n\n\ndef g(a, b):\n    return a + b\n"
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    return _run_mutation_loop(
        selected_sites=discover_sites(src),
        clean_source=src,
        ctx=MutantExecCtx(
            path=str(src_file),
            cwd=str(tmp_path),
            pytest_args=[],
            executor=_FakeExecutor(status="killed"),
            mutant_timeout=5.0,
            test_ctx_db=ctx_db,
            abs_source_path=str(src_file),
        ),
    )


@pytest.mark.unit
def test_run_mutation_loop_tallies_narrowed_selections(tmp_path):
    _, _, selection_counts = _loop_over_two_sites(
        tmp_path, _FakeTestContextDB("narrowed", ["tests/test_calc.py::test_f"])
    )
    assert selection_counts == {"narrowed": 2, "static": 0, "degraded": 0}


@pytest.mark.unit
def test_run_mutation_loop_tallies_static_selections(tmp_path):
    _, _, selection_counts = _loop_over_two_sites(tmp_path, _FakeTestContextDB("static"))
    assert selection_counts == {"narrowed": 0, "static": 2, "degraded": 0}


@pytest.mark.unit
def test_run_mutation_loop_tallies_degraded_selections(tmp_path):
    _, _, selection_counts = _loop_over_two_sites(
        tmp_path, _FakeTestContextDB("under-listed", ["tests/test_calc.py::test_f"])
    )
    assert selection_counts == {"narrowed": 0, "static": 0, "degraded": 2}


@pytest.mark.unit
def test_run_mutation_loop_calls_executor_with_built_args_and_timeout(tmp_path):
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
            mutant_timeout=7.5,
        ),
    )
    assert counts == {"killed": 0, "timeout": 0, "survived": 1}
    assert survivors == discover_sites(src)
    assert executor.calls == [(["-q"], 7.5)]


@pytest.mark.unit
def test_run_mutation_loop_disagreement_aborts_before_applying_the_mutant(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    with pytest.raises(TestSelectionError):
        _run_mutation_loop(
            selected_sites=discover_sites(src),
            clean_source=src,
            ctx=MutantExecCtx(
                path=str(src_file),
                cwd=str(tmp_path),
                pytest_args=[],
                executor=_FakeExecutor(),
                mutant_timeout=5.0,
                test_ctx_db=_FakeTestContextDB("line-absent"),
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
                mutant_timeout=5.0,
                abs_source_path=str(src_file),
            ),
        )
    message = str(excinfo.value)
    assert f"{src_file}:2" in message
    assert hint in message


# ── _run_parallel_workers passes mutant_timeout ───────────────────────────────


@pytest.mark.unit
def test_run_parallel_workers_passes_timeout(tmp_path, monkeypatch):
    """mutant_timeout is forwarded to run_parallel (not silently replaced with None)."""
    import mutate4py._workers as workers_mod

    captured = {}

    def fake_run_parallel(request):
        captured["mutant_timeout"] = request.mutant_timeout
        return ({"killed": 0, "survived": 0, "timeout": 0}, [], None)

    monkeypatch.setattr(workers_mod, "run_parallel", fake_run_parallel)
    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root: None)

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
            mutant_timeout=42.0,
            max_workers=2,
        ),
    )
    assert captured["mutant_timeout"] == 42.0
