"""The Executor line and the Time line, as aggregated: one run's Workers each
describe their own executor (combine_descriptions), and a batch adds each
file's timing into one running total (MutantTiming.merge).
"""

import pytest

from mutate4py._executor import ExecutorDescription, MutantTiming, combine_descriptions


@pytest.mark.unit
def test_workers_that_all_forked_report_forking_with_their_fresh_imports_summed():
    combined = combine_descriptions(
        [ExecutorDescription(mode="forking", fresh_import=2), ExecutorDescription(mode="forking", fresh_import=3)]
    )

    assert combined.render() == "forking (fresh import 5)"


@pytest.mark.unit
def test_workers_that_none_forked_report_the_subprocess_reason_they_share():
    combined = combine_descriptions([ExecutorDescription(mode="subprocess", reason="--no-fork")] * 3)

    assert combined.render() == "subprocess (--no-fork)"


@pytest.mark.unit
def test_a_mix_of_forking_and_subprocess_workers_names_both_modes_and_the_forking_fresh_imports():
    combined = combine_descriptions(
        [
            ExecutorDescription(mode="forking", fresh_import=4),
            ExecutorDescription(mode="subprocess", reason="the forking executor needs a POSIX platform"),
            ExecutorDescription(mode="forking", fresh_import=1),
        ]
    )

    assert combined.render() == (
        "mixed (forking on 2 of 3 workers, fresh import 5; "
        "subprocess on 1 of 3 workers: the forking executor needs a POSIX platform)"
    )


@pytest.mark.unit
def test_combining_no_workers_is_refused_rather_than_reported_as_forking():
    with pytest.raises(ValueError):
        combine_descriptions([])


@pytest.mark.unit
def test_merge_adds_one_files_timing_into_the_running_batch_total():
    total = MutantTiming(mutants_seconds=1.0, mutants_count=1)

    total.merge(
        MutantTiming(
            mutants_seconds=0.5,
            mutants_count=2,
            timeouts_seconds=3.0,
            timeouts_count=1,
            confirmation_seconds=0.25,
            confirmation_runs=1,
            confirmation_kills=1,
        )
    )

    assert total.render() == "Time: mutants 1.50s (3), timeouts 3.00s (1), confirmation 0.25s (1 run, 1 killed)"
