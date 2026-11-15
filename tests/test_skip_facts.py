"""Unit tests for _skip_facts.py (design 89 §5b): the stored Manifests an invocation reads to decide its skip."""

import copy
from pathlib import Path

import pytest

from mutate4py._manifest import build_manifest, embed_manifest, reconcile_manifest
from mutate4py._manifest_storage import write_sidecar_manifest
from mutate4py._skip_facts import skipped_manifests
from mutate4py._tests_fingerprint import tests_fingerprint as fingerprint_of

TESTED_AT = "2026-01-01T00:00:00Z"

SRC = "def f(a, b):\n    return a > b\n\n\ndef g(x):\n    return x + 1\n"

_CLEAN = {"score": {"killed": 1, "survived": 0, "uncovered": 0}, "survivors": [], "accepted": []}
_SCORES = {"func/f": _CLEAN, "func/g": _CLEAN}
_DIGESTS = {"func/f": "digest-f", "func/g": "digest-g"}


def _project(root: Path) -> None:
    (root / "tests").mkdir()
    (root / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n")


def _embed_scored(path: Path, fingerprint: str, *, scores=_SCORES, digests=_DIGESTS, sidecar=False) -> str:
    """Record a scored Manifest for a plain target, carrying the fingerprint the run would write."""
    source = path.read_text()
    manifest = reconcile_manifest(
        None,
        build_manifest(source, tested_at=TESTED_AT),
        scores,
        fresh_digests=digests,
        fingerprint=fingerprint,
    )
    if sidecar:
        write_sidecar_manifest(str(path), manifest)
    else:
        path.write_text(embed_manifest(source, manifest))
    return str(path)


def _scored_target(root: Path, name: str = "f.py", **kwargs) -> str:
    """A target as a scored run leaves it: the plain body is written first, so the fingerprint sees it."""
    path = root / name
    path.write_text(SRC)
    return _embed_scored(path, fingerprint_of(str(root), ""), **kwargs)


def _skip(paths, root, *, manifest_file=False):
    return skipped_manifests(paths, [], str(root), manifest_file=manifest_file)


@pytest.mark.unit
def test_a_complete_unchanged_manifest_with_the_fresh_fingerprint_lets_the_run_skip(tmp_path):
    _project(tmp_path)
    path = _scored_target(tmp_path)

    assert _skip([path], tmp_path) is not None


@pytest.mark.unit
def test_the_sidecar_manifest_of_a_scored_target_lets_the_run_skip(tmp_path):
    _project(tmp_path)
    path = _scored_target(tmp_path, sidecar=True)

    assert _skip([path], tmp_path, manifest_file=True) is not None


@pytest.mark.unit
def test_an_invocation_with_no_targets_never_skips(tmp_path):
    _project(tmp_path)

    assert _skip([], tmp_path) is None


@pytest.mark.unit
def test_a_target_without_a_manifest_blocks_the_skip(tmp_path):
    _project(tmp_path)
    (tmp_path / "f.py").write_text(SRC)

    assert _skip([str(tmp_path / "f.py")], tmp_path) is None


@pytest.mark.unit
def test_a_function_without_a_score_blocks_the_skip(tmp_path):
    _project(tmp_path)
    path = _scored_target(tmp_path, scores={"func/f": _CLEAN})

    assert _skip([path], tmp_path) is None


@pytest.mark.unit
def test_a_function_without_a_tests_digest_blocks_the_skip(tmp_path):
    _project(tmp_path)
    path = _scored_target(tmp_path, digests={"func/f": "digest-f"})

    assert _skip([path], tmp_path) is None


@pytest.mark.unit
def test_an_accepted_survivor_whose_marker_is_missing_blocks_the_skip(tmp_path):
    _project(tmp_path)
    accepted = copy.deepcopy(_SCORES)
    accepted["func/f"] = {
        "score": {"killed": 0, "survived": 1, "uncovered": 0},
        "survivors": [],
        "accepted": [{"line": 2, "desc": "a > b -> a >= b", "reason": "equivalent here"}],
    }
    path = _scored_target(tmp_path, scores=accepted)

    assert _skip([path], tmp_path) is None


@pytest.mark.unit
def test_an_edited_body_blocks_the_skip(tmp_path):
    _project(tmp_path)
    path = _scored_target(tmp_path)
    target = Path(path)
    target.write_text(target.read_text().replace("a > b", "a >= b", 1))

    assert _skip([path], tmp_path) is None


@pytest.mark.unit
def test_an_unparseable_body_blocks_the_skip(tmp_path):
    _project(tmp_path)
    path = _scored_target(tmp_path)
    target = Path(path)
    target.write_text(target.read_text().replace("return a > b", "return a > (", 1))

    assert _skip([path], tmp_path) is None


@pytest.mark.unit
def test_a_leftover_backup_blocks_the_skip(tmp_path):
    _project(tmp_path)
    path = _scored_target(tmp_path)
    (tmp_path / "f.py.bak").write_text(SRC)

    assert _skip([path], tmp_path) is None


@pytest.mark.unit
def test_a_changed_test_file_blocks_the_skip(tmp_path):
    _project(tmp_path)
    path = _scored_target(tmp_path)
    (tmp_path / "tests" / "test_a.py").write_text("def test_a():\n    assert 1 == 1\n")

    assert _skip([path], tmp_path) is None


@pytest.mark.unit
def test_one_unskippable_target_blocks_the_skip_for_the_whole_batch(tmp_path):
    _project(tmp_path)
    scored = _scored_target(tmp_path, "scored.py")
    (tmp_path / "plain.py").write_text(SRC)

    assert _skip([scored, str(tmp_path / "plain.py")], tmp_path) is None


@pytest.mark.unit
def test_a_batch_of_scored_targets_returns_every_manifest(tmp_path):
    _project(tmp_path)
    first, second = tmp_path / "first.py", tmp_path / "second.py"
    first.write_text(SRC)
    second.write_text(SRC)
    fingerprint = fingerprint_of(str(tmp_path), "")
    paths = [_embed_scored(first, fingerprint), _embed_scored(second, fingerprint)]

    manifests = _skip(paths, tmp_path)

    assert manifests is not None
    assert len(manifests) == 2
