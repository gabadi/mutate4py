"""Unit tests for ScoredRun.function_scores (_scoring.py).

Sites are built directly so each case states its coverage and selection inputs.
The scored output for a function is the Manifest's per-function score block.
"""

import pytest

from mutate4py._discovery import Site
from mutate4py._scoring import ScoredRun

_F = "func/f"
_G = "func/g"


def _site(index, line, function_id=_F):
    return Site(
        index=index,
        line=line,
        col=0,
        end_line=line,
        end_col=1,
        function_id=function_id,
        orig_text="a > b",
        mutant_text="a >= b",
        desc=f"d{index}",
    )


@pytest.mark.unit
def test_function_scores_counts():
    s0 = _site(0, line=2)  # covered, survived
    s1 = _site(1, line=3)  # covered, killed
    s2 = _site(2, line=4)  # uncovered
    g0 = _site(3, line=7, function_id=_G)  # covered, killed
    run = ScoredRun(
        all_sites=[s0, s1, s2, g0],
        covered_lines={2, 3, 7},
        selected_sites=[s0, s1, g0],
        survivors=[s0],
    )

    result = run.function_scores([_F])

    assert result == {
        _F: {
            "score": {"killed": 1, "survived": 1, "uncovered": 1},
            "survivors": [{"line": 2, "desc": "d0"}],
            "accepted": [],
        }
    }


@pytest.mark.unit
def test_function_scores_skips_partially_selected_function():
    s0 = _site(0, line=2)
    s1 = _site(1, line=3)  # covered but not selected: the function is partly tested
    g0 = _site(2, line=7, function_id=_G)
    run = ScoredRun(
        all_sites=[s0, s1, g0],
        covered_lines={2, 3, 7},
        selected_sites=[s0, g0],
        survivors=[],
    )

    result = run.function_scores([_F, _G])

    assert _F not in result
    assert _G in result


@pytest.mark.unit
def test_function_scores_skips_uncovered_function_on_narrowed_run():
    s0 = _site(0, line=2)
    s1 = _site(1, line=3)
    run = ScoredRun(all_sites=[s0, s1], covered_lines=set(), selected_sites=[], survivors=[], full_selection=False)

    assert run.function_scores([_F]) == {}


@pytest.mark.unit
def test_function_scores_scores_uncovered_function_on_full_run():
    s0 = _site(0, line=2)
    s1 = _site(1, line=3)
    run = ScoredRun(all_sites=[s0, s1], covered_lines=set(), selected_sites=[], survivors=[], full_selection=True)

    assert run.function_scores([_F]) == {
        _F: {"score": {"killed": 0, "survived": 0, "uncovered": 2}, "survivors": [], "accepted": []}
    }


@pytest.mark.unit
def test_function_scores_skips_function_whose_recorded_survivor_lost_coverage_on_narrowed_run():
    s0 = _site(0, line=2)  # the recorded survivor's Site: no longer covered
    s1 = _site(1, line=3)  # covered and selected
    run = ScoredRun(
        all_sites=[s0, s1],
        covered_lines={3},
        selected_sites=[s1],
        survivors=[],
        recorded_survivors=frozenset({(_F, 2, "d0")}),
    )

    assert run.function_scores([_F]) == {}


@pytest.mark.unit
def test_function_scores_scores_function_whose_recorded_survivor_lost_coverage_on_full_run():
    s0 = _site(0, line=2)
    s1 = _site(1, line=3)
    run = ScoredRun(
        all_sites=[s0, s1],
        covered_lines={3},
        selected_sites=[s1],
        survivors=[],
        full_selection=True,
        recorded_survivors=frozenset({(_F, 2, "d0")}),
    )

    assert run.function_scores([_F]) == {
        _F: {"score": {"killed": 1, "survived": 0, "uncovered": 1}, "survivors": [], "accepted": []}
    }


@pytest.mark.unit
def test_function_scores_recorded_survivor_must_match_site_desc():
    s0 = _site(0, line=2)
    s1 = _site(1, line=3)
    run = ScoredRun(
        all_sites=[s0, s1],
        covered_lines={3},
        selected_sites=[s1],
        survivors=[],
        recorded_survivors=frozenset({(_F, 2, "other")}),
    )

    assert run.function_scores([_F]) == {
        _F: {"score": {"killed": 1, "survived": 0, "uncovered": 1}, "survivors": [], "accepted": []}
    }


@pytest.mark.unit
def test_function_scores_zero_for_function_without_sites():
    run = ScoredRun(
        all_sites=[_site(0, line=2)], covered_lines={2}, selected_sites=[], survivors=[], full_selection=True
    )

    result = run.function_scores(["func/h"])

    assert result == {
        "func/h": {
            "score": {"killed": 0, "survived": 0, "uncovered": 0},
            "survivors": [],
            "accepted": [],
        }
    }


@pytest.mark.unit
def test_function_scores_survivors_sorted_by_index():
    s0 = _site(0, line=3)
    s1 = _site(1, line=2)
    run = ScoredRun(
        all_sites=[s0, s1],
        covered_lines={2, 3},
        selected_sites=[s0, s1],
        survivors=[s1, s0],
    )

    survivors = run.function_scores([_F])[_F]["survivors"]

    assert survivors == [{"line": 3, "desc": "d0"}, {"line": 2, "desc": "d1"}]


@pytest.mark.unit
def test_function_scores_accepted_is_empty():
    s0 = _site(0, line=2)
    run = ScoredRun(all_sites=[s0], covered_lines={2}, selected_sites=[s0], survivors=[s0])

    assert run.function_scores([_F])[_F]["accepted"] == []


@pytest.mark.unit
def test_accepted_survivor_recorded_with_reason():
    s0 = _site(0, line=2)
    run = ScoredRun(
        all_sites=[s0],
        covered_lines={2},
        selected_sites=[s0],
        survivors=[s0],
        markers={2: "same for all inputs"},
    )

    block = run.function_scores([_F])[_F]

    assert block["survivors"] == []
    assert block["accepted"] == [{"line": 2, "desc": "d0", "reason": "same for all inputs"}]


@pytest.mark.unit
def test_marker_accepts_every_site_on_its_line():
    s0 = _site(0, line=2)
    s1 = _site(1, line=2)
    s2 = _site(2, line=3)
    run = ScoredRun(
        all_sites=[s0, s1, s2],
        covered_lines={2, 3},
        selected_sites=[s0, s1, s2],
        survivors=[s0, s1, s2],
        markers={2: "r"},
    )

    block = run.function_scores([_F])[_F]

    assert [a["desc"] for a in block["accepted"]] == ["d0", "d1"]
    assert block["survivors"] == [{"line": 3, "desc": "d2"}]


@pytest.mark.unit
def test_score_survived_counts_accepted():
    s0 = _site(0, line=2)
    s1 = _site(1, line=3)
    run = ScoredRun(
        all_sites=[s0, s1],
        covered_lines={2, 3},
        selected_sites=[s0, s1],
        survivors=[s0, s1],
        markers={2: "r"},
    )

    score = run.function_scores([_F])[_F]["score"]

    assert score == {"killed": 0, "survived": 2, "uncovered": 0}


@pytest.mark.unit
def test_unaccepted_and_accepted_partition_survivors():
    s0 = _site(0, line=2)
    s1 = _site(1, line=3)
    run = ScoredRun(
        all_sites=[s0, s1],
        covered_lines={2, 3},
        selected_sites=[s0, s1],
        survivors=[s1, s0],
        markers={2: "same"},
    )

    assert run.unaccepted() == [s1]
    assert run.accepted() == [(s0, "same")]
