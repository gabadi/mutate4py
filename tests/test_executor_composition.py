"""Integration tests for issue 04a: narrowing (--test-contexts) composing with
the warm forking executor in a single run — real ForkingExecutor, real
TestContextDB, no fakes/stubs. Companion to the fake-executor unit tests in
test_run_mutations_modes.py, which cover the same dispatch logic without
paying for a real fork()/subprocess.
"""

import os
import sqlite3
import sys
import types

import pytest

import mutate4py
import mutate4py._worker_server  # noqa: F401 - self-scan target below relies on this already being imported
from mutate4py._discovery import discover_sites
from mutate4py._forking_executor import ForkingExecutor
from mutate4py._runner import RunMutationsRequest, run_mutations


def _make_functions_source(n: int) -> str:
    lines = []
    for i in range(1, n + 1):
        lines.append(f"def f{i}(a, b):")
        lines.append("    return a + b")
        lines.append("")
    return "\n".join(lines) + "\n"


def _write_lcov(path: str, source_abs: str, covered_lines: list[int]) -> None:
    da_lines = "\n".join(f"DA:{ln},1" for ln in covered_lines)
    content = f"SF:{source_abs}\n{da_lines}\nend_of_record\n"
    with open(path, "w") as f:
        f.write(content)


def _make_coverage_db(db_path: str, source_abs: str, tests_by_line: dict[int, str]) -> None:
    """Minimal .coverage SQLite db (line-only coverage, has_arcs=0): one named
    test context per line, mirroring what an isolated-session build
    (--build-test-contexts) records for a project with one test per function
    under test -- a static context per test, no dynamic-switch phase suffix.
    A |<phase>-suffixed context is a dynamic (pytest-cov switch_context)
    context and downgrades to "degraded" (issue #69); these tests exercise
    narrowed dispatch through a real executor, not that detection path, which
    test_test_selection.py covers directly."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE meta (key TEXT, value TEXT);
        CREATE TABLE file (id INTEGER PRIMARY KEY, path TEXT);
        CREATE TABLE context (id INTEGER PRIMARY KEY, context TEXT);
        CREATE TABLE line_bits (file_id INTEGER, context_id INTEGER, numbits BLOB);
    """)
    cur.execute("INSERT INTO meta(key, value) VALUES ('has_arcs', '0')")
    cur.execute("INSERT INTO file(path) VALUES (?)", (source_abs,))
    file_id = cur.lastrowid
    for line, test_id in tests_by_line.items():
        cur.execute("INSERT INTO context(context) VALUES (?)", (test_id,))
        context_id = cur.lastrowid
        n_bytes = (line + 7) // 8
        data = bytearray(n_bytes)
        byte_idx = (line - 1) // 8
        bit_idx = (line - 1) % 8
        data[byte_idx] |= 1 << bit_idx
        cur.execute(
            "INSERT INTO line_bits(file_id, context_id, numbits) VALUES (?, ?, ?)",
            (file_id, context_id, bytes(data)),
        )
    conn.commit()
    conn.close()


def _write_per_function_pytest_project(cwd: str, n: int) -> None:
    import os

    tests_dir = os.path.join(cwd, "tests")
    os.makedirs(tests_dir, exist_ok=True)
    with open(os.path.join(cwd, "conftest.py"), "w") as f:
        f.write("")
    lines = ["from calc import " + ", ".join(f"f{i}" for i in range(1, n + 1))]
    for i in range(1, n + 1):
        lines.append(f"def test_f{i}():")
        lines.append(f"    assert f{i}(2, 2) == 4")
    with open(os.path.join(tests_dir, "test_calc.py"), "w") as f:
        f.write("\n".join(lines) + "\n")


# --- per-call args vary within one primed forking session ---------------------


@pytest.mark.integration
def test_forking_executor_honors_different_args_within_one_primed_session(tmp_path):
    """The composition property this ticket is about: one primed session must
    run a *different* argv per run() call, not a fixed args list — otherwise
    per-site test-context narrowing could never reach the forking executor."""
    cwd = str(tmp_path)
    (tmp_path / "conftest.py").write_text("")
    target = tmp_path / "calc.py"
    target.write_text("def add(a, b):\n    return a + b\ndef sub(a, b):\n    return a - b\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_calc.py").write_text(
        "from calc import add, sub\n"
        "def test_add():\n    assert add(2, 2) == 4\n"
        "def test_sub_wrong():\n    assert sub(2, 2) == 1\n"  # always-failing on purpose
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=str(target))
    executor.prime()

    assert executor.run(["-q", "tests/test_calc.py::test_add"], timeout=30.0) == "survived"
    assert executor.run(["-q", "tests/test_calc.py::test_sub_wrong"], timeout=30.0) == "killed"
    assert executor.run(["-q", "tests/test_calc.py::test_add"], timeout=30.0) == "survived"


# --- real ForkingExecutor + real TestContextDB via run_mutations --------------


@pytest.mark.integration
def test_forking_executor_composes_with_real_test_context_db(tmp_path, monkeypatch):
    """End-to-end: run_mutations selects the forking executor (default,
    unguarded now that the test_ctx_db exclusion is gone) and narrows each
    mutant's args per real TestContextDB lookups."""
    import mutate4py._forking_executor as forking_mod

    created = []
    real_cls = forking_mod.ForkingExecutor

    class _TrackingForkingExecutor(real_cls):
        def __init__(self, *a, **kw):
            created.append(self)
            super().__init__(*a, **kw)

    monkeypatch.setattr(forking_mod, "ForkingExecutor", _TrackingForkingExecutor)

    cwd = str(tmp_path)
    src = _make_functions_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    _write_per_function_pytest_project(cwd, 3)

    sites = discover_sites(src)
    assert len(sites) == 3
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov(lcov_path, src_path, [s.line for s in sites])

    db_path = str(tmp_path / ".coverage")
    _make_coverage_db(db_path, src_path, {s.line: f"tests/test_calc.py::test_f{i}" for i, s in enumerate(sites, 1)})

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                cov_cmd=None,
                lcov_path=lcov_path,
                reuse_coverage=False,
                pytest_args=["-q", "tests"],
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                cwd=cwd,
                test_contexts_path=db_path,
            )
        )
    output = buf.getvalue()
    assert rc == 0
    assert "Test selection: narrowed 3, static 0, degraded 0" in output
    assert len(created) == 1, "expected the real forking executor to be instantiated exactly once"


# --- leaked-target degrades to subprocess, still classifies correctly ---------


def test_leaked_target_degrades_to_subprocess_and_still_narrows_correctly(tmp_path, monkeypatch):
    """A module-leak (forking ineligible for safety, not composition) must
    still fall back cleanly to the subprocess executor and preserve correct
    narrowed-dispatch classification — composition degrades, it doesn't break."""
    import mutate4py._subprocess_executor as subprocess_mod

    created = []
    real_cls = subprocess_mod.SubprocessExecutor

    class _TrackingSubprocessExecutor(real_cls):
        def __init__(self, *a, **kw):
            created.append(self)
            super().__init__(*a, **kw)

    monkeypatch.setattr(subprocess_mod, "SubprocessExecutor", _TrackingSubprocessExecutor)

    cwd = str(tmp_path)
    src = _make_functions_source(2)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    _write_per_function_pytest_project(cwd, 2)

    sites = discover_sites(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov(lcov_path, src_path, [s.line for s in sites])

    db_path = str(tmp_path / ".coverage")
    _make_coverage_db(db_path, src_path, {s.line: f"tests/test_calc.py::test_f{i}" for i, s in enumerate(sites, 1)})

    fake_module = types.ModuleType("calc")
    fake_module.__file__ = src_path
    monkeypatch.setitem(sys.modules, "calc", fake_module)

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                cov_cmd=None,
                lcov_path=lcov_path,
                reuse_coverage=False,
                pytest_args=["-q", "tests"],
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                cwd=cwd,
                test_contexts_path=db_path,
            )
        )
    output = buf.getvalue()
    assert rc == 0
    assert "Test selection: narrowed 2, static 0, degraded 0" in output
    assert len(created) == 1, "expected the subprocess fallback to actually be used"


# --- executor parity: forking vs subprocess classify an identical mutant the same


@pytest.mark.integration
def test_forking_and_subprocess_executors_classify_the_same_mutant_identically(tmp_path):
    from mutate4py._subprocess_executor import SubprocessExecutor

    cwd = str(tmp_path)
    (tmp_path / "conftest.py").write_text("")
    target = tmp_path / "calc.py"
    target.write_text("def add(a, b):\n    return a + b\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_calc.py").write_text("from calc import add\ndef test_add():\n    assert add(2, 2) == 4\n")
    args = ["-q", "tests"]

    forking = ForkingExecutor(cwd=cwd, guarded_path=str(target))
    forking.prime()
    subprocess_executor = SubprocessExecutor(cwd=cwd)
    subprocess_executor.prime()

    # Unmutated: both must report "survived".
    assert forking.run(args, timeout=30.0) == "survived"
    assert subprocess_executor.run(args, timeout=30.0) == "survived"

    # Mutated (+ -> -): both must report "killed".
    target.write_text("def add(a, b):\n    return a - b\n")
    assert forking.run(args, timeout=30.0) == "killed"
    assert subprocess_executor.run(args, timeout=30.0) == "killed"


# --- self-scan on the project's own orchestrator modules ----------------------


@pytest.mark.integration
def test_self_scan_on_worker_server_degrades_to_subprocess_and_kills_correctly(tmp_path, monkeypatch):
    """mutate4py._worker_server — issue 04b's Worker subprocess entry point —
    is already imported by this test process (module-level import above), so
    scanning its real on-disk file is a genuine self-leak, not a synthetic
    tmp_path fixture: exactly the "self-referential scanning" hazard
    AGENTS.md warns about. Must still degrade to the subprocess executor and
    still classify mutants on the real file correctly.

    _executor_selection.py (this test's target before this session) lost all
    real mutation sites when issue 04b's own refactor inlined the old
    _forking_eligible's boolean logic into _runner.py instead of moving it
    there — _prepare_executor's remaining body has no Compare/BoolOp/BinOp
    node discover_sites recognizes. _worker_server.py's `main()` still has
    the forking_flag comparison this ticket's Worker-selection wiring
    depends on, so it replaces _executor_selection.py as this test's target.
    """
    import mutate4py._forking_executor as forking_mod
    import mutate4py._subprocess_executor as subprocess_mod

    target = os.path.join(os.path.dirname(mutate4py.__file__), "_worker_server.py")
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(mutate4py.__file__))))
    assert os.path.isfile(os.path.join(repo_root, "tests", "test_worker_protocol.py")), "repo_root miscomputed"

    with open(target) as f:
        original = f.read()
    sites = discover_sites(original)
    assert sites, "expected real mutation sites in _worker_server.py"

    created_forking = []
    created_subprocess = []
    real_forking_cls = forking_mod.ForkingExecutor
    real_subprocess_cls = subprocess_mod.SubprocessExecutor

    class _TrackingForkingExecutor(real_forking_cls):
        def __init__(self, *a, **kw):
            created_forking.append(self)
            super().__init__(*a, **kw)

    class _TrackingSubprocessExecutor(real_subprocess_cls):
        def __init__(self, *a, **kw):
            created_subprocess.append(self)
            super().__init__(*a, **kw)

    monkeypatch.setattr(forking_mod, "ForkingExecutor", _TrackingForkingExecutor)
    monkeypatch.setattr(subprocess_mod, "SubprocessExecutor", _TrackingSubprocessExecutor)

    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov(lcov_path, target, [s.line for s in sites])

    try:
        rc = run_mutations(
            RunMutationsRequest(
                path=target,
                source=original,
                cov_cmd=None,
                lcov_path=lcov_path,
                reuse_coverage=False,
                pytest_args=["-q", "tests/test_worker_protocol.py", "-k", "leaked or round_trip"],
                timeout_factor=20,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                cwd=repo_root,
            )
        )
    finally:
        with open(target, "w") as f:
            f.write(original)

    assert rc == 0
    assert len(created_forking) == 1, "expected the forking executor to be attempted once"
    assert len(created_subprocess) == 1, "expected the self-leak to fall back to the subprocess executor"
    # A main() mutant must be killed by test_worker_protocol.py's own assertions.
    assert any(s.function_id == "func/main" for s in sites)
