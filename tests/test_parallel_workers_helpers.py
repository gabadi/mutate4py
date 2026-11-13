"""Unit tests for acceptance/steps/parallel_workers_helpers.py."""

import os

import pytest

from acceptance.steps.parallel_workers_helpers import (
    Placement,
    assert_measured_in_original,
    assert_mutants_ran_in_workers,
    assert_original_never_spliced,
    assert_worker_tree_seen_during_run,
    parse_placements,
    placement_probe,
    read_placements,
    report_tally,
    survivor_lines,
)


@pytest.mark.unit
def test_probe_appends_cwd_tree_flag_and_splice_flag(tmp_path):
    record = tmp_path / "record.txt"
    source = tmp_path / "sample.py"
    source.write_text("return a > b\n")
    workers = tmp_path / ".mutate4py" / "workers"
    exec(placement_probe(str(record), str(workers), str(source)))
    workers.mkdir(parents=True)
    source.write_text("return a >= b\n")
    exec(placement_probe(str(record), str(workers), str(source)))
    cwd = os.getcwd()
    assert record.read_text() == f"{cwd}|False|False\n{cwd}|True|True\n"


@pytest.mark.unit
def test_parse_placements_reads_one_record_per_line():
    assert parse_placements("/a|False|False\n/b|True|True\n") == [
        Placement("/a", False, False),
        Placement("/b", True, True),
    ]
    assert parse_placements("") == []


@pytest.mark.unit
def test_read_placements_fails_on_a_missing_or_empty_record(tmp_path):
    with pytest.raises(AssertionError, match="no test recorded"):
        read_placements(str(tmp_path / "missing.txt"))
    empty = tmp_path / "empty.txt"
    empty.write_text("")
    with pytest.raises(AssertionError, match="holds no records"):
        read_placements(str(empty))
    full = tmp_path / "full.txt"
    full.write_text("/a|False|False\n")
    assert read_placements(str(full)) == [Placement("/a", False, False)]


@pytest.mark.unit
def test_measured_in_original_accepts_the_project_dir_with_no_worker_tree(tmp_path):
    placements = [Placement(str(tmp_path), False, False)] * 2
    assert_measured_in_original(placements, str(tmp_path), 2)


@pytest.mark.unit
def test_measured_in_original_rejects_another_directory(tmp_path):
    placements = [Placement(str(tmp_path), False, False), Placement(str(tmp_path / "elsewhere"), False, False)]
    with pytest.raises(AssertionError, match="should run in"):
        assert_measured_in_original(placements, str(tmp_path), 2)


@pytest.mark.unit
def test_measured_in_original_rejects_a_worker_tree_that_already_exists(tmp_path):
    with pytest.raises(AssertionError, match="before the Measurement"):
        assert_measured_in_original([Placement(str(tmp_path), True, False)], str(tmp_path), 1)


@pytest.mark.unit
def test_measured_in_original_needs_every_test_recorded(tmp_path):
    with pytest.raises(AssertionError, match="recorded 1 of 2"):
        assert_measured_in_original([Placement(str(tmp_path), False, False)], str(tmp_path), 2)


@pytest.mark.unit
def test_mutants_ran_in_workers_accepts_runs_under_the_worker_tree(tmp_path):
    worker = tmp_path / ".mutate4py" / "workers" / "run1" / "worker-1"
    placements = [Placement(str(tmp_path), False, False), Placement(str(worker), True, False)]
    assert_mutants_ran_in_workers(placements, str(tmp_path), 1)


@pytest.mark.unit
def test_mutants_ran_in_workers_rejects_a_run_in_the_original(tmp_path):
    placements = [Placement(str(tmp_path), False, False), Placement(str(tmp_path), True, False)]
    with pytest.raises(AssertionError, match="mutated runs outside"):
        assert_mutants_ran_in_workers(placements, str(tmp_path), 1)


@pytest.mark.unit
def test_mutants_ran_in_workers_skips_the_measured_records_and_needs_a_mutated_run(tmp_path):
    placements = [Placement(str(tmp_path), False, False)] * 2
    with pytest.raises(AssertionError, match="no mutated test run"):
        assert_mutants_ran_in_workers(placements, str(tmp_path), 2)


@pytest.mark.unit
def test_worker_tree_seen_requires_every_mutated_run_to_see_it():
    measured = Placement("/a", False, False)
    assert_worker_tree_seen_during_run([measured, Placement("/b", True, False)], 1)
    with pytest.raises(AssertionError, match="saw no worker tree"):
        assert_worker_tree_seen_during_run([measured, Placement("/b", False, False)], 1)
    with pytest.raises(AssertionError, match="no mutated test run"):
        assert_worker_tree_seen_during_run([measured], 1)


@pytest.mark.unit
def test_original_never_spliced_rejects_a_spliced_original():
    assert_original_never_spliced([Placement("/a", False, False), Placement("/b", True, False)])
    with pytest.raises(AssertionError, match="held a Mutant"):
        assert_original_never_spliced([Placement("/a", False, False), Placement("/b", True, True)])


REPORT = """Mutation Report
===============
Killed: 3
Survived: 1
Uncovered: 0

Survivors:
  line 2 a > b -> a >= b func/f1
  line 5 a > b -> a >= b func/f2

Time: mutants 0.20s (2)
"""


@pytest.mark.unit
def test_report_tally_reads_the_count_on_a_report_line():
    assert report_tally(REPORT, "Killed") == 3
    assert report_tally(REPORT, "Survived") == 1


@pytest.mark.unit
def test_report_tally_fails_when_the_line_is_missing():
    with pytest.raises(AssertionError, match="no 'Timeout' line"):
        report_tally(REPORT, "Timeout")


@pytest.mark.unit
def test_survivor_lines_stop_at_the_end_of_the_block():
    assert survivor_lines(REPORT) == [
        "line 2 a > b -> a >= b func/f1",
        "line 5 a > b -> a >= b func/f2",
    ]


@pytest.mark.unit
def test_survivor_lines_of_a_report_without_survivors_is_empty():
    assert survivor_lines("Mutation Report\nKilled: 1\n") == []
