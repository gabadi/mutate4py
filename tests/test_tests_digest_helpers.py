"""Unit tests for acceptance/steps/tests_digest_helpers.py."""

import json

import pytest

from acceptance.steps.tests_digest_helpers import (
    RECORDED_HEADER,
    edited,
    recorded_survivor_ids,
    rescored_function_ids,
    survivor_ids,
    without_digests,
)

REPORT = """\
Mutation run: sur.py
[1/3] survived line 6 a > b + 0 -> a >= b + 0: func/other
[2/3] survived line 6 b + 0 -> b - 0: func/other
[3/3] killed line 6 0 -> 1: func/other

Mutation Report
===============
Killed: 1

Survivors:
  line 6 a > b + 0 -> a >= b + 0 func/other
  line 6 b + 0 -> b - 0 func/other

Time: mutants 1.04s (3)

Recorded survivors (function unchanged, not re-run):
  line 2 a > b -> a >= b func/keep

Measurement: 0.50s, 2 tests, core ctrace
"""


@pytest.mark.unit
def test_edited_adds_one_comment_line():
    assert edited("x = 1\n") == "x = 1\n# edited\n"


@pytest.mark.unit
def test_rescored_function_ids_come_from_progress_lines_once_each():
    assert rescored_function_ids(REPORT) == ["func/other"]


@pytest.mark.unit
def test_rescored_function_ids_keep_run_order():
    out = "[1/2] killed line 2 a + b -> a - b: func/inc\n[2/2] killed line 6 a - b -> a + b: func/dec\n"

    assert rescored_function_ids(out) == ["func/inc", "func/dec"]


@pytest.mark.unit
def test_rescored_function_ids_empty_when_nothing_ran():
    assert rescored_function_ids("Mutation Report\n===============\nKilled: 0\n") == []


@pytest.mark.unit
def test_survivor_ids_read_only_the_runs_own_block():
    assert survivor_ids(REPORT) == ["func/other"]


@pytest.mark.unit
def test_recorded_survivor_ids_read_only_the_recorded_block():
    assert recorded_survivor_ids(REPORT) == ["func/keep"]


@pytest.mark.unit
def test_blocks_are_empty_when_the_header_is_absent():
    assert survivor_ids("Killed: 1\n") == []
    assert recorded_survivor_ids("Killed: 1\n") == []


@pytest.mark.unit
def test_recorded_header_is_the_report_line():
    assert RECORDED_HEADER in REPORT.splitlines()


@pytest.mark.unit
def test_without_digests_drops_only_the_digests_from_the_embedded_manifest():
    manifest = {"version": 1, "functions": [{"id": "func/f", "tests_digest": "abc", "score": {"killed": 1}}]}
    source = f"def f():\n    pass\n\n# mutate4py-manifest-begin\n# {json.dumps(manifest)}\n# mutate4py-manifest-end\n"

    got = without_digests(source)

    (line,) = [ln for ln in got.splitlines() if ln.startswith("# {")]
    (fn,) = json.loads(line[2:])["functions"]
    assert fn == {"id": "func/f", "score": {"killed": 1}}
    assert got.startswith("def f():\n    pass\n\n# mutate4py-manifest-begin\n")
    assert got.endswith("# mutate4py-manifest-end\n")
