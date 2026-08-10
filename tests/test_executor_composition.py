"""Integration tests for issue 04a: narrowing (--test-contexts) composing with
the warm forking executor in a single run — real ForkingExecutor, real
TestContextDB, no fakes/stubs. Companion to the fake-executor unit tests in
test_run_mutations_modes.py, which cover the same dispatch logic without
paying for a real fork()/subprocess.
"""

import sqlite3
import sys
import types

import pytest

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
    test context per line, mirroring what coverage.py's dynamic-context mode
    actually records for a project with one test per function under test."""
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
        cur.execute("INSERT INTO context(context) VALUES (?)", (f"{test_id}|run",))
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
    assert "Test selection: narrowed 3, static 0" in output
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
    assert "Test selection: narrowed 2, static 0" in output
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
