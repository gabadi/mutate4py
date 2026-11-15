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
def test_a_method_marker_of_the_same_reason_does_not_hide_a_removed_class_body_marker():
    from mutate4py._equivalent import marker_lines
    from mutate4py._manifest import functions_with_unmarked_acceptances

    reason = "same for all inputs"
    marked = (
        "class C:\n"
        f"    flag = LIMIT > 0  # mutate4py: equivalent {reason}\n"
        "\n"
        "    def m(self, a, b):\n"
        f"        return a > b  # mutate4py: equivalent {reason}\n"
    )
    class_marker_removed = marked.replace(f"LIMIT > 0  # mutate4py: equivalent {reason}", "LIMIT > 0")
    manifest = build_manifest(marked, tested_at=TESTED_AT)
    _fn(manifest, "class/C").update(
        score=_F_SCORE, survivors=[], accepted=[{"line": 2, "desc": "LIMIT > 0 -> LIMIT >= 0", "reason": reason}]
    )
    _fn(manifest, "func/C.m").update(
        score=_F_SCORE, survivors=[], accepted=[{"line": 5, "desc": "a > b -> a >= b", "reason": reason}]
    )
    current = build_manifest(class_marker_removed, tested_at=TESTED_LATER)

    unmarked = functions_with_unmarked_acceptances(manifest, current, marker_lines(class_marker_removed))

    assert unmarked == {"class/C"}


@pytest.mark.unit
def test_unmarked_acceptances_none_is_empty():
    from mutate4py._manifest import functions_with_unmarked_acceptances

    current = build_manifest(_MARKED_SRC, tested_at=TESTED_LATER)

    assert functions_with_unmarked_acceptances(None, current, {}) == set()


# ── tests_digest: carried with the score, replaced on rescore, adopted ──────


def _with_digest(manifest, digests):
    """Test setup: stamp tests_digest onto the named function entries."""
    for fn in manifest["functions"]:
        if fn["id"] in digests:
            fn["tests_digest"] = digests[fn["id"]]
    return manifest


@pytest.mark.unit
def test_rescored_function_takes_the_fresh_digest():
    from mutate4py._manifest import reconcile_manifest

    existing = _with_digest(_scored(SRC, tested_at=TESTED_AT), {"func/f": "old"})
    candidate = build_manifest(SRC, tested_at=TESTED_LATER)

    result = reconcile_manifest(existing, candidate, _SCORES, fresh_digests={"func/f": "new"})

    assert result is not existing
    assert _fn(result, "func/f")["tests_digest"] == "new"


@pytest.mark.unit
def test_digest_only_change_on_a_rescored_function_returns_a_new_manifest():
    """Acceptance (e): the unchanged check compares digests, so a rescore that moves only the digest writes."""
    from mutate4py._manifest import reconcile_manifest

    existing = _with_digest(_scored(SRC, tested_at=TESTED_AT), {"func/f": "same", "func/g": "old"})
    candidate = build_manifest(SRC, tested_at=TESTED_LATER)

    result = reconcile_manifest(existing, candidate, _SCORES, fresh_digests={"func/f": "same", "func/g": "moved"})

    assert result is not existing
    assert _fn(result, "func/g")["tests_digest"] == "moved"
    assert _fn(result, "func/g")["score"] == _fn(existing, "func/g")["score"]


@pytest.mark.unit
def test_stored_digest_is_carried_while_the_hash_is_unchanged():
    from mutate4py._manifest import reconcile_manifest

    existing = _with_digest(_scored(SRC, tested_at=TESTED_AT), {"func/f": "old"})
    candidate = build_manifest(SRC_G_CHANGED, tested_at=TESTED_LATER)

    result = reconcile_manifest(existing, candidate)

    assert _fn(result, "func/f")["tests_digest"] == "old"


@pytest.mark.unit
def test_stored_digest_is_dropped_when_the_hash_changes():
    from mutate4py._manifest import reconcile_manifest

    existing = _with_digest(_scored(SRC, tested_at=TESTED_AT), {"func/g": "old"})
    candidate = build_manifest(SRC_G_CHANGED, tested_at=TESTED_LATER)

    result = reconcile_manifest(existing, candidate)

    assert "tests_digest" not in _fn(result, "func/g")


@pytest.mark.unit
def test_stored_digest_that_differs_is_kept_when_the_function_is_not_rescored():
    from mutate4py._manifest import reconcile_manifest

    existing = _with_digest(_scored(SRC, tested_at=TESTED_AT), {"func/g": "old"})
    candidate = build_manifest(SRC, tested_at=TESTED_LATER)

    result = reconcile_manifest(existing, candidate, fresh_digests={"func/g": "new"})

    assert result is existing
    assert _fn(result, "func/g")["tests_digest"] == "old"


@pytest.mark.unit
def test_clean_entry_without_digest_adopts_the_fresh_digest_without_a_rescore():
    from mutate4py._manifest import reconcile_manifest

    existing = _scored(SRC, tested_at=TESTED_AT)
    candidate = build_manifest(SRC, tested_at=TESTED_LATER)

    result = reconcile_manifest(existing, candidate, fresh_digests={"func/g": "fresh"})

    assert result is not existing
    assert _fn(result, "func/g")["tests_digest"] == "fresh"
    assert _fn(result, "func/g")["score"] == _G_SCORE


@pytest.mark.unit
def test_entry_with_survivors_does_not_adopt_a_digest():
    from mutate4py._manifest import reconcile_manifest

    existing = _scored(SRC, tested_at=TESTED_AT)
    candidate = build_manifest(SRC, tested_at=TESTED_LATER)

    result = reconcile_manifest(existing, candidate, fresh_digests={"func/f": "fresh"})

    assert "tests_digest" not in _fn(result, "func/f")


@pytest.mark.unit
def test_unscored_entry_does_not_adopt_a_digest():
    from mutate4py._manifest import reconcile_manifest

    existing = build_manifest(SRC, tested_at=TESTED_AT)
    candidate = build_manifest(SRC, tested_at=TESTED_LATER)

    result = reconcile_manifest(existing, candidate, fresh_digests={"func/g": "fresh"})

    assert result is existing
    assert "tests_digest" not in _fn(result, "func/g")


@pytest.mark.unit
def test_entry_from_0_2_x_keeps_its_score_and_has_no_tests_digest_key():
    from mutate4py._manifest import reconcile_manifest

    existing = _scored(SRC, tested_at=TESTED_AT)
    candidate = build_manifest(SRC, tested_at=TESTED_LATER)

    result = reconcile_manifest(existing, candidate)

    assert result["version"] == 1
    assert _fn(result, "func/f")["score"] == _F_SCORE
    assert "tests_digest" not in _fn(result, "func/f")


@pytest.mark.unit
def test_tests_digest_round_trips_through_the_embedded_footer():
    from mutate4py._manifest import embed_manifest, extract_manifest

    manifest = _with_digest(_scored(SRC, tested_at=TESTED_AT), {"func/f": "abc"})

    stored, ok = extract_manifest(embed_manifest(SRC, manifest))

    assert ok
    assert stored["version"] == 1
    assert _fn(stored, "func/f")["tests_digest"] == "abc"
    assert "tests_digest" not in _fn(stored, "func/g")


# ── functions_with_survivors: only while the entry has no tests_digest (#106) ─


@pytest.mark.unit
def test_functions_with_survivors_skips_an_entry_that_has_a_digest():
    from mutate4py._manifest import functions_with_survivors

    manifest = _with_digest(_scored(SRC), {"func/f": "stored"})

    assert functions_with_survivors(manifest) == set()


@pytest.mark.unit
def test_functions_with_survivors_names_only_the_entry_without_a_digest():
    from mutate4py._manifest import functions_with_survivors

    manifest = _with_digest(_scored(SRC), {"func/f": "stored"})
    _fn(manifest, "func/g").update(score=_F_SCORE, survivors=_F_SURVIVORS, accepted=[])

    assert functions_with_survivors(manifest) == {"func/g"}


# ── functions_with_changed_digest: stored digest differs from this run's (#106) ─


@pytest.mark.unit
def test_functions_with_changed_digest_names_a_stored_digest_that_differs():
    from mutate4py._digest_changes import functions_with_changed_digest

    manifest = _with_digest(_scored(SRC), {"func/f": "old", "func/g": "same"})

    assert functions_with_changed_digest(manifest, {"func/f": "new", "func/g": "same"}) == {"func/f"}


@pytest.mark.unit
def test_functions_with_changed_digest_ignores_an_entry_without_a_stored_digest():
    """No stored digest is adoption (ADR 0026 precedent), not a change."""
    from mutate4py._digest_changes import functions_with_changed_digest

    manifest = _scored(SRC)

    assert functions_with_changed_digest(manifest, {"func/f": "new", "func/g": "new"}) == set()


@pytest.mark.unit
def test_functions_with_changed_digest_ignores_a_function_with_no_fresh_digest():
    from mutate4py._digest_changes import functions_with_changed_digest

    manifest = _with_digest(_scored(SRC), {"func/f": "old", "func/g": "old"})

    assert functions_with_changed_digest(manifest, {"func/g": "old"}) == set()


@pytest.mark.unit
def test_functions_with_changed_digest_none_is_empty():
    from mutate4py._digest_changes import functions_with_changed_digest

    assert functions_with_changed_digest(None, {"func/f": "new"}) == set()


# ── recorded-survivor block: apart from this run's Survivors (#106) ───────────


@pytest.mark.unit
def test_recorded_block_lines_format():
    from mutate4py._report import _recorded_block_lines

    lines = _recorded_block_lines([("func/f", {"line": 2, "desc": "a > b -> a >= b"})])

    assert lines == [
        "",
        "Recorded survivors (function unchanged, not re-run):",
        "  line 2 a > b -> a >= b func/f",
    ]


@pytest.mark.unit
def test_recorded_block_lines_empty():
    from mutate4py._report import _recorded_block_lines

    assert _recorded_block_lines([]) == []
