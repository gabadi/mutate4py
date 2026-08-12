"""End-to-end proof for `build_test_context_db` and the bug it replaces.

Uses tests/fixtures/overlapping_coverage/ (shared.py + two tests, test_from_a
and test_from_b, that both call shared()) to show:

- build_test_context_db (isolated coverage.py session per test, then
  `coverage combine`) attributes shared()'s line to BOTH tests.
- the rejected alternative -- one shared `pytest --cov-context=test` session
  -- attributes the same line to only the first test that touches it.

See docs/adr/0021-test-context-db-isolated-session-build.md.
"""

import os
import subprocess
import sys

import pytest

import mutate4py._forking_executor
from mutate4py._forking_executor import ForkingExecutor
from mutate4py._test_context_build import (
    TestContextBuildError,
    _combine_argv,
    _run_argv,
    build_test_context_db,
)
from mutate4py._test_selection import TestContextDB

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "overlapping_coverage")
SHARED_PY = os.path.join(FIXTURE_DIR, "shared.py")
NODE_IDS = ["test_a.py::test_from_a", "test_b.py::test_from_b"]
SHARED_LINE = 2  # `return 1` inside shared() -- executed by both tests
ONLY_A_LINE = 6  # `return "a"` inside only_a() -- test_from_a only
ONLY_B_LINE = 10  # `return "b"` inside only_b() -- test_from_b only


def test_run_argv_names_one_static_context_per_test():
    argv = _run_argv("test_a.py::test_from_a", data_file=".coverage.0", pytest_args=["-q"], python_executable="python")
    assert argv == [
        "python",
        "-m",
        "coverage",
        "run",
        "--context=test_a.py::test_from_a",
        "--data-file=.coverage.0",
        "-m",
        "pytest",
        "test_a.py::test_from_a",
        "-q",
    ]


def test_combine_argv_lists_every_data_file():
    argv = _combine_argv([".coverage.0", ".coverage.1"], output_db_path="combined.coverage", python_executable="python")
    assert argv == [
        "python",
        "-m",
        "coverage",
        "combine",
        "--data-file=combined.coverage",
        ".coverage.0",
        ".coverage.1",
    ]


def test_empty_node_ids_raises_before_touching_coverage():
    with pytest.raises(TestContextBuildError, match="no test node IDs"):
        build_test_context_db([], cwd=FIXTURE_DIR, output_db_path="unused.coverage")


@pytest.mark.integration
def test_isolated_session_build_narrows_to_every_covering_test(tmp_path):
    db_path = str(tmp_path / "combined.coverage")

    build_test_context_db(NODE_IDS, cwd=FIXTURE_DIR, output_db_path=db_path)

    db = TestContextDB(db_path)
    try:
        assert db.tests_for_line(SHARED_PY, SHARED_LINE) == ("narrowed", sorted(NODE_IDS))
        assert db.tests_for_line(SHARED_PY, ONLY_A_LINE) == ("narrowed", ["test_a.py::test_from_a"])
        assert db.tests_for_line(SHARED_PY, ONLY_B_LINE) == ("narrowed", ["test_b.py::test_from_b"])
    finally:
        db.close()


def test_isolated_session_runner_non_survived_raises_build_error(tmp_path):
    """The seam _dispatch.py's forking path uses (issue #51): a runner
    result other than "survived" must raise, same as a nonzero subprocess
    exit does for the cold path."""

    def fake_runner(node_id: str, data_file: str, pytest_args: list[str]) -> str:
        return "killed"

    with pytest.raises(TestContextBuildError, match="did not run cleanly"):
        build_test_context_db(
            ["test_a.py::test_from_a"],
            cwd=FIXTURE_DIR,
            output_db_path=str(tmp_path / "unused.coverage"),
            isolated_session_runner=fake_runner,
        )


@pytest.mark.integration
def test_isolated_session_runner_produces_same_narrowing_as_cold_build(tmp_path):
    """Equivalence: injecting a runner (the seam _dispatch.py's forking path
    uses) must narrow context db lines identically to the cold subprocess
    build (see test_isolated_session_build_narrows_to_every_covering_test
    above) -- proves build_test_context_db's per-node_id loop and its final
    combine step behave the same regardless of which executor produced each
    per-test data file."""
    db_path = str(tmp_path / "combined.coverage")
    calls: list[str] = []

    def fake_runner(node_id: str, data_file: str, pytest_args: list[str]) -> str:
        calls.append(node_id)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "coverage",
                "run",
                f"--context={node_id}",
                f"--data-file={data_file}",
                "-m",
                "pytest",
                node_id,
                *pytest_args,
            ],
            cwd=FIXTURE_DIR,
            capture_output=True,
            text=True,
        )
        return "survived" if result.returncode == 0 else "killed"

    build_test_context_db(NODE_IDS, cwd=FIXTURE_DIR, output_db_path=db_path, isolated_session_runner=fake_runner)

    assert calls == NODE_IDS

    db = TestContextDB(db_path)
    try:
        assert db.tests_for_line(SHARED_PY, SHARED_LINE) == ("narrowed", sorted(NODE_IDS))
        assert db.tests_for_line(SHARED_PY, ONLY_A_LINE) == ("narrowed", ["test_a.py::test_from_a"])
        assert db.tests_for_line(SHARED_PY, ONLY_B_LINE) == ("narrowed", ["test_b.py::test_from_b"])
    finally:
        db.close()


@pytest.mark.integration
def test_real_forking_executor_narrows_identically_to_cold_build_on_one_target(tmp_path, monkeypatch):
    """AC3 (issue #51), tightened: the real ForkingExecutor-backed runner
    (not a stand-in subprocess) and the cold subprocess path must narrow
    identically on the exact same target -- not just on two separately
    constructed, structurally-identical fixtures.

    Built under tmp_path, not tests/fixtures/overlapping_coverage/ (FIXTURE_DIR
    above): priming then forking inside this repo's own tree deadlocks under
    pytest-tach's fork-time lock (see
    test_forking_executor._write_coverage_fixture_project's docstring) --
    every real-ForkingExecutor test in this codebase uses a fresh tmp_path
    fixture for the same reason.

    isolated_coverage_session_safe stubbed True: tach.pytest_plugin is an
    always-on plugin in this dev venv, loaded before this test module even
    starts collecting, so the real gate would refuse unconditionally here --
    that gate has its own dedicated tests in test_forking_executor.py; this
    test isolates build_test_context_db's cold/warm equivalence instead.
    """
    monkeypatch.setattr(mutate4py._forking_executor, "isolated_coverage_session_safe", lambda: True)
    cwd = str(tmp_path)
    (tmp_path / ".coveragerc").write_text("[run]\nbranch = True\n")
    (tmp_path / "shared.py").write_text(
        "def shared():\n    return 1\n\n\ndef only_a():\n    return 'a'\n\n\ndef only_b():\n    return 'b'\n"
    )
    (tmp_path / "test_a.py").write_text(
        "from shared import only_a, shared\n\n\ndef test_from_a():\n    assert shared() == 1\n"
        "    assert only_a() == 'a'\n"
    )
    (tmp_path / "test_b.py").write_text(
        "from shared import only_b, shared\n\n\ndef test_from_b():\n    assert shared() == 1\n"
        "    assert only_b() == 'b'\n"
    )
    node_ids = ["test_a.py::test_from_a", "test_b.py::test_from_b"]
    shared_py = str(tmp_path / "shared.py")
    lines = (2, 6, 10)  # shared() / only_a() / only_b() return statements

    cold_db_path = str(tmp_path / "cold.coverage")
    build_test_context_db(node_ids, cwd=cwd, output_db_path=cold_db_path)

    executor = ForkingExecutor(cwd=cwd, guarded_path=cwd)
    executor.prime()

    def real_runner(node_id: str, data_file: str, pytest_args: list[str]) -> str:
        return executor.run_isolated_coverage_session(
            node_id, data_file=data_file, pytest_args=pytest_args, timeout=30.0
        )

    warm_db_path = str(tmp_path / "warm.coverage")
    build_test_context_db(node_ids, cwd=cwd, output_db_path=warm_db_path, isolated_session_runner=real_runner)

    cold_db = TestContextDB(cold_db_path)
    warm_db = TestContextDB(warm_db_path)
    try:
        for line in lines:
            assert cold_db.tests_for_line(shared_py, line) == warm_db.tests_for_line(shared_py, line)
    finally:
        cold_db.close()
        warm_db.close()


@pytest.mark.integration
def test_single_shared_session_under_lists_covering_tests(tmp_path):
    """Regression test for the rejected alternative: one shared
    `pytest --cov-context=test` session drops every test after the first
    to reach a shared line -- the exact defect isolated sessions fix.

    Issue #69: TestContextDB itself now detects this and refuses to return
    "narrowed" for a line whose covering tests include a dynamic
    (switch_context) context -- see test_test_selection.py's under-listed
    tests for the unit-level coverage of the detection rule this exercises
    end-to-end, against a real coverage.py db.
    """
    db_path = tmp_path / ".coverage"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "test_a.py::test_from_a",
            "test_b.py::test_from_b",
            "--cov=.",
            "--cov-branch",
            "--cov-context=test",
            "--cov-report=",
            "-p",
            "pytest_cov",
            "-q",
        ],
        cwd=FIXTURE_DIR,
        env={**os.environ, "COVERAGE_FILE": str(db_path)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    db = TestContextDB(str(db_path))
    try:
        outcome, node_ids = db.tests_for_line(SHARED_PY, SHARED_LINE)
        # The bug: only one of the two tests that cover this line survives,
        # not both -- an isolated-session build (see the test above) would
        # list both. Which one survives is whichever pytest happened to run
        # first, not something this test should pin down. Issue #69: this is
        # exactly why the outcome is "under-listed", not "narrowed" -- a
        # single dynamic-context test in the list is enough evidence the
        # list may be incomplete, so mutate4py must not run only it. pytest
        # computes this context's nodeid relative to the rootdir it
        # discovers by walking up from FIXTURE_DIR (this repo's own
        # pyproject.toml), so only the suffix is checked, not the exact
        # string.
        assert outcome == "under-listed"
        assert len(node_ids) == 1
        assert node_ids[0].endswith("test_from_a") or node_ids[0].endswith("test_from_b")
    finally:
        db.close()
