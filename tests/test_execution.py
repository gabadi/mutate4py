"""Unit tests for the mutant execution engine (_execution.py)."""

import pytest

from mutate4py._discovery import discover_sites
from mutate4py._execution import (
    MutantExecCtx,
    TestSelectionError,
    _build_mutant_command,
    _run_mutation_loop,
    _run_parallel_workers,
    _run_single_mutant,
)

# ── _build_mutant_command ───────────────────────────────────────────────────────


class _FakeTestContextDB:
    def __init__(self, outcome, node_ids=()):
        self._result = (outcome, list(node_ids))

    def tests_for_line(self, source_path, line):
        return self._result


def _one_site(src="def f(a, b):\n    return a > b\n"):
    return discover_sites(src)[0]


def test_build_mutant_command_no_ctx_db_returns_full_command():
    assert _build_mutant_command("pytest", None, "/src/calc.py", _one_site()) == (
        "pytest",
        None,
    )


def test_build_mutant_command_narrows_to_covering_tests():
    ctx_db = _FakeTestContextDB("narrowed", ["tests/test_calc.py::test_gt"])
    assert _build_mutant_command("pytest", ctx_db, "/src/calc.py", _one_site()) == (
        "pytest tests/test_calc.py::test_gt",
        "narrowed",
    )


def test_build_mutant_command_quotes_node_ids():
    ctx_db = _FakeTestContextDB("narrowed", ["tests/t.py::test_a[x y]"])
    cmd, _ = _build_mutant_command("pytest", ctx_db, "/src/calc.py", _one_site())
    assert cmd == "pytest 'tests/t.py::test_a[x y]'"


def test_build_mutant_command_static_line_runs_full_command():
    ctx_db = _FakeTestContextDB("static")
    assert _build_mutant_command("pytest", ctx_db, "/src/calc.py", _one_site()) == (
        "pytest",
        "static",
    )


@pytest.mark.parametrize(
    "outcome, hint",
    [
        ("line-absent", "absent from the test-context db"),
        ("file-absent", "not in the test-context db"),
    ],
)
def test_build_mutant_command_disagreement_raises(outcome, hint):
    ctx_db = _FakeTestContextDB(outcome)
    with pytest.raises(TestSelectionError) as excinfo:
        _build_mutant_command("pytest", ctx_db, "/src/calc.py", _one_site())
    message = str(excinfo.value)
    assert "/src/calc.py:2" in message
    assert hint in message


def test_build_mutant_command_unrecognized_outcome_raises():
    """No outcome may fall through to a full-suite run counted as narrowed."""
    ctx_db = _FakeTestContextDB("something-new")
    with pytest.raises(TestSelectionError, match="unrecognized selection outcome"):
        _build_mutant_command("pytest", ctx_db, "/src/calc.py", _one_site())


# ── _run_mutation_loop ────────────────────────────────────────────────────────


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
            test_command="exit 0",
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
            test_command="exit 1",
            mutant_timeout=5.0,
            test_ctx_db=ctx_db,
            abs_source_path=str(src_file),
        ),
    )


def test_run_mutation_loop_tallies_narrowed_selections(tmp_path):
    _, _, selection_counts = _loop_over_two_sites(
        tmp_path, _FakeTestContextDB("narrowed", ["tests/test_calc.py::test_f"])
    )
    assert selection_counts == {"narrowed": 2, "static": 0}


def test_run_mutation_loop_tallies_static_selections(tmp_path):
    _, _, selection_counts = _loop_over_two_sites(tmp_path, _FakeTestContextDB("static"))
    assert selection_counts == {"narrowed": 0, "static": 2}


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
                test_command="exit 1",
                mutant_timeout=5.0,
                test_ctx_db=_FakeTestContextDB("line-absent"),
                abs_source_path=str(src_file),
            ),
        )
    assert src_file.read_text() == src


# ── _run_single_mutant ────────────────────────────────────────────────────────


def test_run_single_mutant_uses_fork_server_when_given():
    class FakeForkServer:
        def run(self, timeout):
            return "survived", False

    status = _run_single_mutant(FakeForkServer(), "pytest", "/cwd", 5.0)
    assert status == "survived"


def test_run_single_mutant_falls_back_to_subprocess_when_no_fork_server():
    status = _run_single_mutant(None, "exit 1", "/tmp", 5.0)
    assert status == "killed"


# ── _run_parallel_workers passes mutant_timeout ───────────────────────────────


def test_run_parallel_workers_passes_timeout(tmp_path, monkeypatch):
    """mutant_timeout is forwarded to run_parallel (not silently replaced with None)."""
    import mutate4py._workers as workers_mod

    captured = {}

    def fake_run_parallel(request):
        captured["mutant_timeout"] = request.mutant_timeout
        return ({"killed": 0, "survived": 0, "timeout": 0}, [])

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
            test_command="exit 0",
            mutant_timeout=42.0,
            max_workers=2,
        ),
    )
    assert captured["mutant_timeout"] == 42.0
