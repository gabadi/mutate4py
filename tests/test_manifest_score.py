"""Unit tests for Manifest score keys and the survivor/unscored helpers.

Functions are imported inside each test so that a helper which does not exist
yet fails only the tests that use it.
"""

import pytest

from mutate4py._manifest import build_manifest

TESTED_AT = "2026-01-01T00:00:00Z"
TESTED_LATER = "2026-02-02T00:00:00Z"

SRC = "def f(a, b):\n    return a > b\n\n\ndef g(x):\n    return x + 1\n"
SRC_G_CHANGED = "def f(a, b):\n    return a > b\n\n\ndef g(x):\n    return x + 2\n"

_F_SCORE = {"killed": 0, "survived": 1, "uncovered": 0}
_G_SCORE = {"killed": 1, "survived": 0, "uncovered": 0}
_F_SURVIVORS = [{"line": 2, "desc": "a > b -> a >= b"}]

_SCORES = {
    "func/f": {"score": _F_SCORE, "survivors": _F_SURVIVORS, "accepted": []},
    "func/g": {"score": _G_SCORE, "survivors": [], "accepted": []},
}


def _apply_scores(manifest, scores):
    """Test setup: stamp score keys onto a built manifest's function entries."""
    for fn in manifest["functions"]:
        entry = scores[fn["id"]]
        fn["score"] = entry["score"]
        fn["survivors"] = entry["survivors"]
        fn["accepted"] = entry["accepted"]
    return manifest


def _scored(source=SRC, tested_at=TESTED_AT):
    return _apply_scores(build_manifest(source, tested_at=tested_at), _SCORES)


def _fn(manifest, fid):
    return next(fn for fn in manifest["functions"] if fn["id"] == fid)


# ── reconcile_manifest: keep, drop, override, identity ───────────────────────


@pytest.mark.unit
def test_reconcile_keeps_scored_fields_for_unchanged_function():
    from mutate4py._manifest import reconcile_manifest

    existing = _scored(SRC)
    candidate = build_manifest(SRC_G_CHANGED, tested_at=TESTED_LATER)

    result = reconcile_manifest(existing, candidate)

    f = _fn(result, "func/f")
    assert f["score"] == _F_SCORE
    assert f["survivors"] == _F_SURVIVORS
    assert f["accepted"] == []


@pytest.mark.unit
def test_reconcile_drops_scored_fields_for_changed_function():
    from mutate4py._manifest import reconcile_manifest

    existing = _scored(SRC)
    candidate = build_manifest(SRC_G_CHANGED, tested_at=TESTED_LATER)

    result = reconcile_manifest(existing, candidate)

    g = _fn(result, "func/g")
    assert set(g) == {"id", "name", "line", "end_line", "hash"}


@pytest.mark.unit
def test_reconcile_run_scores_override_existing():
    from mutate4py._manifest import reconcile_manifest

    existing = _scored(SRC)
    candidate = build_manifest(SRC, tested_at=TESTED_LATER)
    new_f_score = {"killed": 1, "survived": 0, "uncovered": 0}
    scores = {"func/f": {"score": new_f_score, "survivors": [], "accepted": []}}

    result = reconcile_manifest(existing, candidate, scores)

    assert _fn(result, "func/f")["score"] == new_f_score
    assert _fn(result, "func/f")["survivors"] == []


@pytest.mark.unit
def test_reconcile_returns_existing_object_when_structure_and_scores_equal():
    from mutate4py._manifest import reconcile_manifest

    existing = _scored(SRC, tested_at=TESTED_AT)
    candidate = build_manifest(SRC, tested_at=TESTED_LATER)

    result = reconcile_manifest(existing, candidate, _SCORES)

    assert result is existing


@pytest.mark.unit
def test_reconcile_returns_new_manifest_when_only_scores_change():
    from mutate4py._manifest import reconcile_manifest

    existing = _scored(SRC, tested_at=TESTED_AT)
    candidate = build_manifest(SRC, tested_at=TESTED_LATER)
    scores = {
        "func/f": {"score": {"killed": 1, "survived": 0, "uncovered": 0}, "survivors": [], "accepted": []},
        "func/g": {"score": _G_SCORE, "survivors": [], "accepted": []},
    }

    result = reconcile_manifest(existing, candidate, scores)

    assert result is not existing
    assert result["tested_at"] == TESTED_LATER
    assert _fn(result, "func/f")["score"] == {"killed": 1, "survived": 0, "uncovered": 0}


@pytest.mark.unit
def test_reconcile_writes_canonical_key_order():
    from mutate4py._manifest import reconcile_manifest

    candidate = build_manifest(SRC, tested_at=TESTED_AT)
    scores = {
        "func/f": {
            "score": {"uncovered": 0, "survived": 1, "killed": 0},
            "accepted": [],
            "survivors": _F_SURVIVORS,
        },
        "func/g": {"score": _G_SCORE, "survivors": [], "accepted": []},
    }

    result = reconcile_manifest(None, candidate, scores)

    f = _fn(result, "func/f")
    assert list(f) == ["id", "name", "line", "end_line", "hash", "score", "survivors", "accepted"]
    assert list(f["score"]) == ["killed", "survived", "uncovered"]


@pytest.mark.unit
def test_structural_equality_ignores_score_keys():
    from mutate4py._manifest import manifests_structurally_equal

    plain = build_manifest(SRC, tested_at=TESTED_AT)
    scored = _scored(SRC, tested_at=TESTED_AT)

    assert manifests_structurally_equal(plain, scored)


@pytest.mark.unit
def test_scored_fields_tolerates_missing_lists():
    from mutate4py._manifest import is_unscored, recorded_survivors

    manifest = build_manifest(SRC, tested_at=TESTED_AT)
    for fn in manifest["functions"]:
        fn["score"] = {"killed": 1, "survived": 0, "uncovered": 0}

    assert recorded_survivors(manifest) == []
    assert is_unscored(manifest) is False


@pytest.mark.unit
def test_scored_fields_tolerates_null_lists():
    from mutate4py._manifest import functions_with_survivors, is_unscored, recorded_survivors

    manifest = build_manifest(SRC, tested_at=TESTED_AT)
    for fn in manifest["functions"]:
        fn["score"] = {"killed": 1, "survived": 0, "uncovered": 0}
        fn["survivors"] = None
        fn["accepted"] = None
    manifest["functions"][0]["survivors"] = [None, "x"]

    assert recorded_survivors(manifest) == []
    assert functions_with_survivors(manifest) == set()
    assert is_unscored(manifest) is False


# ── functions_with_survivors / recorded_survivors ───────────────────────────


@pytest.mark.unit
def test_functions_with_survivors():
    from mutate4py._manifest import functions_with_survivors

    manifest = _scored(SRC)

    assert functions_with_survivors(manifest) == {"func/f"}


@pytest.mark.unit
def test_functions_with_survivors_none_is_empty():
    from mutate4py._manifest import functions_with_survivors

    assert functions_with_survivors(None) == set()


@pytest.mark.unit
def test_recorded_survivors_order():
    from mutate4py._manifest import recorded_survivors

    manifest = build_manifest(SRC, tested_at=TESTED_AT)
    f_survivors = [{"line": 3, "desc": "second"}, {"line": 2, "desc": "first"}]
    g_survivors = [{"line": 6, "desc": "third"}]
    _fn(manifest, "func/f").update(score=_F_SCORE, survivors=f_survivors, accepted=[])
    _fn(manifest, "func/g").update(score=_F_SCORE, survivors=g_survivors, accepted=[])

    assert recorded_survivors(manifest) == [
        ("func/f", {"line": 3, "desc": "second"}),
        ("func/f", {"line": 2, "desc": "first"}),
        ("func/g", {"line": 6, "desc": "third"}),
    ]


# ── is_unscored ─────────────────────────────────────────────────────────


@pytest.mark.unit
def test_is_unscored_for_014_manifest():
    from mutate4py._manifest import is_unscored

    assert is_unscored(build_manifest(SRC, tested_at=TESTED_AT)) is True


@pytest.mark.unit
def test_is_unscored_false_when_all_scored():
    from mutate4py._manifest import is_unscored

    assert is_unscored(_scored(SRC)) is False


@pytest.mark.unit
def test_is_unscored_false_with_no_functions():
    from mutate4py._manifest import is_unscored

    manifest = build_manifest("x = 1\n", tested_at=TESTED_AT)

    assert manifest["functions"] == []
    assert is_unscored(manifest) is False


@pytest.mark.unit
def test_is_unscored_true_when_mixed():
    from mutate4py._manifest import is_unscored

    manifest = _scored(SRC)
    del _fn(manifest, "func/g")["score"]

    assert is_unscored(manifest) is True


# ── functions_with_unmarked_acceptances (accepted survivor's marker gone) ────

_MARKED_SRC = "def f(a, b):\n    return a > b  # mutate4py: equivalent same for all inputs\n"
_F_ACCEPTED = [{"line": 2, "desc": "a > b -> a >= b", "reason": "same for all inputs"}]


def _accepted_manifest(source):
    manifest = build_manifest(source, tested_at=TESTED_AT)
    _fn(manifest, "func/f").update(score=_F_SCORE, survivors=[], accepted=_F_ACCEPTED)
    return manifest


@pytest.mark.unit
def test_unmarked_acceptance_detected_when_marker_removed():
    from mutate4py._equivalent import marker_lines
    from mutate4py._manifest import functions_with_unmarked_acceptances

    unmarked = "def f(a, b):\n    return a > b\n"
    current = build_manifest(unmarked, tested_at=TESTED_LATER)

    assert functions_with_unmarked_acceptances(_accepted_manifest(_MARKED_SRC), current, marker_lines(unmarked)) == {
        "func/f"
    }


@pytest.mark.unit
def test_unmarked_acceptance_not_detected_when_code_moves():
    from mutate4py._equivalent import marker_lines
    from mutate4py._manifest import functions_with_unmarked_acceptances

    moved = "\n" + _MARKED_SRC
    current = build_manifest(moved, tested_at=TESTED_LATER)

    assert functions_with_unmarked_acceptances(_accepted_manifest(_MARKED_SRC), current, marker_lines(moved)) == set()


@pytest.mark.unit
def test_unmarked_acceptance_detected_when_reason_edited():
    from mutate4py._equivalent import marker_lines
    from mutate4py._manifest import functions_with_unmarked_acceptances

    reworded = "def f(a, b):\n    return a > b  # mutate4py: equivalent different reason\n"
    current = build_manifest(reworded, tested_at=TESTED_LATER)

    assert functions_with_unmarked_acceptances(_accepted_manifest(_MARKED_SRC), current, marker_lines(reworded)) == {
        "func/f"
    }


@pytest.mark.unit
def test_unmarked_acceptance_detected_when_one_of_two_same_reason_markers_removed():
    from mutate4py._equivalent import marker_lines
    from mutate4py._manifest import functions_with_unmarked_acceptances

    two_sites = (
        "def f(a, b):\n"
        "    x = a > b  # mutate4py: equivalent same for all inputs\n"
        "    return a < b  # mutate4py: equivalent same for all inputs\n"
    )
    one_removed = "def f(a, b):\n    x = a > b\n    return a < b  # mutate4py: equivalent same for all inputs\n"
    accepted = [
        {"line": 2, "desc": "a > b -> a >= b", "reason": "same for all inputs"},
        {"line": 3, "desc": "a < b -> a <= b", "reason": "same for all inputs"},
    ]
    manifest = build_manifest(two_sites, tested_at=TESTED_AT)
    _fn(manifest, "func/f").update(score=_F_SCORE, survivors=[], accepted=accepted)
    current = build_manifest(one_removed, tested_at=TESTED_LATER)

    assert functions_with_unmarked_acceptances(manifest, current, marker_lines(one_removed)) == {"func/f"}


@pytest.mark.unit
def test_unmarked_acceptances_none_is_empty():
    from mutate4py._manifest import functions_with_unmarked_acceptances

    current = build_manifest(_MARKED_SRC, tested_at=TESTED_LATER)

    assert functions_with_unmarked_acceptances(None, current, {}) == set()
