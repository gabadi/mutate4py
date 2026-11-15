"""functions_unscored: the functions a run scores because no stored score block covers them (ADR 0029 rule 1)."""

import pytest

from mutate4py._manifest import build_manifest, is_unscored
from mutate4py._unscored import functions_unscored

TESTED_AT = "2026-01-01T00:00:00Z"
SRC = "def f(a, b):\n    return a > b\n\n\ndef g(x):\n    return x + 1\n"
SCORE = {"killed": 1, "survived": 0, "uncovered": 0}


def _with_scores(manifest, *fids):
    """Test setup: stamp a score block onto the named function entries."""
    for fn in manifest["functions"]:
        if fn["id"] in fids:
            fn.update(score=SCORE, survivors=[], accepted=[])
    return manifest


@pytest.mark.unit
def test_no_stored_manifest_gives_no_unscored_functions():
    assert functions_unscored(None, build_manifest(SRC, tested_at=TESTED_AT)) == set()


@pytest.mark.unit
def test_stored_entries_without_score_blocks_are_all_unscored():
    current = build_manifest(SRC, tested_at=TESTED_AT)
    stored = build_manifest(SRC, tested_at=TESTED_AT)

    assert functions_unscored(stored, current) == {"func/f", "func/g"}


@pytest.mark.unit
def test_scored_entries_are_not_unscored():
    current = build_manifest(SRC, tested_at=TESTED_AT)
    stored = _with_scores(build_manifest(SRC, tested_at=TESTED_AT), "func/f", "func/g")

    assert functions_unscored(stored, current) == set()


@pytest.mark.unit
def test_only_the_entry_without_a_score_block_is_reported():
    current = build_manifest(SRC, tested_at=TESTED_AT)
    stored = _with_scores(build_manifest(SRC, tested_at=TESTED_AT), "func/f")

    assert functions_unscored(stored, current) == {"func/g"}


@pytest.mark.unit
def test_function_missing_from_stored_manifest_is_unscored():
    current = build_manifest(SRC + "\n\ndef h(x):\n    return x\n", tested_at=TESTED_AT)
    stored = _with_scores(build_manifest(SRC, tested_at=TESTED_AT), "func/f", "func/g")

    assert functions_unscored(stored, current) == {"func/h"}


@pytest.mark.unit
@pytest.mark.parametrize("scored", [(), ("func/f",), ("func/f", "func/g")])
def test_agrees_with_is_unscored(scored):
    current = build_manifest(SRC, tested_at=TESTED_AT)
    stored = _with_scores(build_manifest(SRC, tested_at=TESTED_AT), *scored)

    assert bool(functions_unscored(stored, current)) == is_unscored(stored)
