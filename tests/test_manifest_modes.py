"""Unit tests for the no-run Manifest modes with score keys (_manifest_modes.py).

Covers --check-manifest's survivor gate and unscored note, and
--update-manifest's idempotence and score dropping. Each test runs in both
storages where the behaviour is storage-independent.
"""

import logging

import pytest

from mutate4py._manifest import build_manifest, embed_manifest, extract_manifest
from mutate4py._manifest_modes import check_manifest, update_manifest
from mutate4py._manifest_storage import read_sidecar_manifest, write_sidecar_manifest

TESTED_AT = "2026-01-01T00:00:00Z"
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
    for fn in manifest["functions"]:
        entry = scores[fn["id"]]
        fn["score"] = entry["score"]
        fn["survivors"] = entry["survivors"]
        fn["accepted"] = entry["accepted"]
    return manifest


def _read_stored(path, manifest_file):
    if manifest_file:
        return read_sidecar_manifest(path)[0]
    return extract_manifest(_read_source(path))[0]


def _store(path, clean, manifest, manifest_file):
    if manifest_file:
        with open(path, "w") as f:
            f.write(clean)
        write_sidecar_manifest(path, manifest)
    else:
        with open(path, "w") as f:
            f.write(embed_manifest(clean, manifest))


def _snapshot(path, manifest_file):
    with open(path, "rb") as f:
        source_bytes = f.read()
    if not manifest_file:
        return source_bytes
    with open(path + ".manifest.json", "rb") as f:
        return source_bytes, f.read()


def _read_source(path):
    with open(path) as f:
        return f.read()


# ── --check-manifest: survivor gate ─────────────────────────────────────


@pytest.mark.unit
def test_check_manifest_fails_on_recorded_survivor_even_when_sha_matches(tmp_path):
    path = str(tmp_path / "calc.py")
    manifest = _apply_scores(build_manifest(SRC, tested_at=TESTED_AT), _SCORES)
    _store(path, SRC, manifest, manifest_file=True)

    assert check_manifest(path=path, source=SRC, manifest_file=True) == 1


@pytest.mark.unit
def test_check_manifest_names_file_function_and_survivor(tmp_path, caplog):
    path = str(tmp_path / "calc.py")
    manifest = _apply_scores(build_manifest(SRC, tested_at=TESTED_AT), _SCORES)
    _store(path, SRC, manifest, manifest_file=True)

    with caplog.at_level(logging.INFO):
        check_manifest(path=path, source=SRC, manifest_file=True)

    assert "Manifest has survivors: " + path in caplog.text
    assert "line 2 a > b -> a >= b func/f" in caplog.text


# ── --check-manifest: unscored note ─────────────────────────────────────


@pytest.mark.unit
def test_check_manifest_prints_unscored_for_014_manifest_and_exits_0(tmp_path, caplog):
    path = str(tmp_path / "calc.py")
    _store(path, SRC, build_manifest(SRC, tested_at=TESTED_AT), manifest_file=True)

    with caplog.at_level(logging.INFO):
        rc = check_manifest(path=path, source=SRC, manifest_file=True)

    assert rc == 0
    assert "Manifest current: " + path + " (unscored)" in caplog.text


@pytest.mark.unit
def test_check_manifest_no_unscored_suffix_when_scored(tmp_path, caplog):
    path = str(tmp_path / "calc.py")
    clean_scores = {
        "func/f": {"score": _G_SCORE, "survivors": [], "accepted": []},
        "func/g": {"score": _G_SCORE, "survivors": [], "accepted": []},
    }
    manifest = _apply_scores(build_manifest(SRC, tested_at=TESTED_AT), clean_scores)
    _store(path, SRC, manifest, manifest_file=True)

    with caplog.at_level(logging.INFO):
        rc = check_manifest(path=path, source=SRC, manifest_file=True)

    assert rc == 0
    assert "Manifest current: " + path in caplog.text
    assert "(unscored)" not in caplog.text


# ── --check-manifest: accepted survivor whose marker was removed ────────


@pytest.mark.unit
def test_check_manifest_fails_when_accepted_marker_removed(tmp_path, caplog):
    path = str(tmp_path / "calc.py")
    marked = SRC.replace("return a > b\n", "return a > b  # mutate4py: equivalent same for all inputs\n", 1)
    accepted_scores = {
        "func/f": {
            "score": _F_SCORE,
            "survivors": [],
            "accepted": [{"line": 2, "desc": "a > b -> a >= b", "reason": "same for all inputs"}],
        },
        "func/g": {"score": _G_SCORE, "survivors": [], "accepted": []},
    }
    accepted = _apply_scores(build_manifest(marked, tested_at=TESTED_AT), accepted_scores)
    _store(path, marked, accepted, manifest_file=True)

    with caplog.at_level(logging.INFO):
        rc = check_manifest(path=path, source=SRC, manifest_file=True)

    messages = [r.getMessage() for r in caplog.records]
    assert rc == 1
    assert f"Manifest stale: {path}" in messages
    assert "  func/f: an accepted survivor's equivalent marker was removed or changed" in messages


@pytest.mark.unit
@pytest.mark.parametrize("manifest_file", [True, False], ids=["sidecar", "embedded"])
def test_check_manifest_fails_when_accepted_marker_removed_after_update(tmp_path, caplog, manifest_file):
    path = str(tmp_path / "calc.py")
    accepted_scores = {
        "func/f": {
            "score": _F_SCORE,
            "survivors": [],
            "accepted": [{"line": 2, "desc": "a > b -> a >= b", "reason": "same for all inputs"}],
        },
        "func/g": {"score": _G_SCORE, "survivors": [], "accepted": []},
    }
    # An update rewrites source_sha256 from the unmarked source but keeps the recorded reason.
    manifest = _apply_scores(build_manifest(SRC, tested_at=TESTED_AT), accepted_scores)
    _store(path, SRC, manifest, manifest_file)

    with caplog.at_level(logging.INFO):
        rc = check_manifest(path=path, source=_read_source(path), manifest_file=manifest_file)

    messages = [r.getMessage() for r in caplog.records]
    assert rc == 1
    assert "  func/f: an accepted survivor's equivalent marker was removed or changed" in messages


# ── --update-manifest: idempotence and score dropping ───────────────────


@pytest.mark.unit
@pytest.mark.parametrize("manifest_file", [True, False], ids=["sidecar", "embedded"])
def test_update_manifest_idempotent_with_scores(tmp_path, caplog, manifest_file):
    path = str(tmp_path / "calc.py")
    assert update_manifest(path=path, source=_seed(path, SRC), manifest_file=manifest_file) == 0
    _store(path, SRC, _apply_scores(_read_stored(path, manifest_file), _SCORES), manifest_file)
    before = _snapshot(path, manifest_file)
    caplog.clear()

    with caplog.at_level(logging.INFO):
        rc = update_manifest(path=path, source=_read_source(path), manifest_file=manifest_file)

    assert rc == 0
    assert "Manifest unchanged" in caplog.text
    assert _snapshot(path, manifest_file) == before


@pytest.mark.unit
@pytest.mark.parametrize("manifest_file", [True, False], ids=["sidecar", "embedded"])
def test_update_manifest_drops_scores_of_changed_function(tmp_path, manifest_file):
    path = str(tmp_path / "calc.py")
    assert update_manifest(path=path, source=_seed(path, SRC), manifest_file=manifest_file) == 0
    scored = _apply_scores(_read_stored(path, manifest_file), _SCORES)
    _store(path, SRC_G_CHANGED, scored, manifest_file)

    assert update_manifest(path=path, source=_read_source(path), manifest_file=manifest_file) == 0

    stored = _read_stored(path, manifest_file)
    f = next(fn for fn in stored["functions"] if fn["id"] == "func/f")
    g = next(fn for fn in stored["functions"] if fn["id"] == "func/g")
    assert f["score"] == _F_SCORE
    assert "score" not in g


def _seed(path, clean):
    """Write the clean source and return the text --update-manifest reads from it."""
    with open(path, "w") as f:
        f.write(clean)
    return clean
