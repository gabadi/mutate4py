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


@pytest.mark.integration
def test_single_shared_session_under_lists_covering_tests(tmp_path):
    """Regression test for the rejected alternative: one shared
    `pytest --cov-context=test` session drops every test after the first
    to reach a shared line -- the exact defect isolated sessions fix.
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
        assert outcome == "narrowed"
        # The bug: only one of the two tests that cover this line survives,
        # not both -- an isolated-session build (see the test above) would
        # list both. Which one survives is whichever pytest happened to run
        # first, not something this test should pin down. pytest computes
        # this context's nodeid relative to the rootdir it discovers by
        # walking up from FIXTURE_DIR (this repo's own pyproject.toml), so
        # only the suffix is checked, not the exact string.
        assert len(node_ids) == 1
        assert node_ids[0].endswith("test_from_a") or node_ids[0].endswith("test_from_b")
    finally:
        db.close()
