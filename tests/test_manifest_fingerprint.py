"""Unit tests for the tests fingerprint a scored run records in the Manifest (design 89 §5b).

The functions are imported inside each test so that a parameter which does not
exist yet fails only the tests that use it.
"""

import pytest

from mutate4py._manifest import build_manifest

TESTED_AT = "2026-01-01T00:00:00Z"
TESTED_LATER = "2026-02-02T00:00:00Z"

SRC = "def f(a, b):\n    return a > b\n\n\ndef g(x):\n    return x + 1\n"

_SCORES = {
    "func/f": {
        "score": {"killed": 0, "survived": 1, "uncovered": 0},
        "survivors": [{"line": 2, "desc": "a > b -> a >= b"}],
        "accepted": [],
    },
    "func/g": {
        "score": {"killed": 1, "survived": 0, "uncovered": 0},
        "survivors": [],
        "accepted": [],
    },
}


@pytest.mark.unit
def test_scored_reconcile_writes_the_fingerprint_into_the_manifest():
    from mutate4py._manifest import reconcile_manifest

    candidate = build_manifest(SRC, tested_at=TESTED_AT)

    result = reconcile_manifest(None, candidate, _SCORES, fingerprint="fp-new")

    assert result["tests_fingerprint"] == "fp-new"


@pytest.mark.unit
def test_a_fingerprint_only_change_is_written_not_returned_by_identity():
    from mutate4py._manifest import reconcile_manifest

    existing = reconcile_manifest(None, build_manifest(SRC, tested_at=TESTED_AT), _SCORES, fingerprint="fp-old")
    candidate = build_manifest(SRC, tested_at=TESTED_LATER)

    result = reconcile_manifest(existing, candidate, _SCORES, fingerprint="fp-new")

    assert result is not existing
    assert result["tests_fingerprint"] == "fp-new"


@pytest.mark.unit
def test_an_unchanged_fingerprint_keeps_the_existing_object():
    from mutate4py._manifest import reconcile_manifest

    existing = reconcile_manifest(None, build_manifest(SRC, tested_at=TESTED_AT), _SCORES, fingerprint="fp-same")
    candidate = build_manifest(SRC, tested_at=TESTED_LATER)

    result = reconcile_manifest(existing, candidate, _SCORES, fingerprint="fp-same")

    assert result is existing


@pytest.mark.unit
def test_a_run_without_a_fingerprint_keeps_the_stored_one():
    from mutate4py._manifest import reconcile_manifest

    existing = reconcile_manifest(None, build_manifest(SRC, tested_at=TESTED_AT), _SCORES, fingerprint="fp-old")
    candidate = build_manifest(SRC, tested_at=TESTED_LATER)

    result = reconcile_manifest(existing, candidate, _SCORES)

    assert result is existing
    assert result["tests_fingerprint"] == "fp-old"


class _CompletedRunStub:
    """Stands in for ScoredRun: every named function scored clean in a run that completed."""

    def function_scores(self, function_ids):
        return {
            fid: {"score": {"killed": 1, "survived": 0, "uncovered": 0}, "survivors": [], "accepted": []}
            for fid in function_ids
        }


def _footer_tests_fingerprint(path):
    import json

    with open(path) as f:
        content = f.read()
    manifest_line = [ln for ln in content.splitlines() if ln.startswith("# {")][0]
    return json.loads(manifest_line[2:]).get("tests_fingerprint")


@pytest.mark.unit
def test_finalize_source_records_the_fingerprint_of_a_completed_scored_run(tmp_path):
    from mutate4py._manifest_storage import ManifestLocation
    from mutate4py._source_loading import _finalize_source

    src_path = str(tmp_path / "f.py")
    with open(src_path, "w") as f:
        f.write(SRC)

    _finalize_source(
        SRC,
        TESTED_AT,
        src_path + ".bak",
        ManifestLocation(path=src_path),
        scored_run=_CompletedRunStub(),
        fingerprint="fp-new",
    )

    assert _footer_tests_fingerprint(src_path) == "fp-new"


@pytest.mark.unit
def test_finalize_source_of_an_unscored_run_keeps_the_stored_fingerprint(tmp_path):
    from mutate4py._manifest import reconcile_manifest
    from mutate4py._manifest_storage import ManifestLocation
    from mutate4py._source_loading import _finalize_source

    src_path = str(tmp_path / "f.py")
    with open(src_path, "w") as f:
        f.write(SRC)
    existing = reconcile_manifest(None, build_manifest(SRC, tested_at=TESTED_AT), _SCORES, fingerprint="fp-old")

    _finalize_source(
        SRC,
        TESTED_LATER,
        src_path + ".bak",
        ManifestLocation(path=src_path),
        existing_manifest=existing,
        scored_run=None,
        fingerprint="fp-new",
    )

    assert _footer_tests_fingerprint(src_path) == "fp-old"


class _ScoredNothingStub:
    """Stands in for ScoredRun in a run that completed but wrote no score block: every function was skipped."""

    def function_scores(self, function_ids):
        return {}


@pytest.mark.unit
def test_finalize_source_of_a_run_that_scored_nothing_records_the_fresh_fingerprint(tmp_path):
    """A completed run records its fingerprint even when it writes no score block (spec 5b)."""
    from mutate4py._manifest import reconcile_manifest
    from mutate4py._manifest_storage import ManifestLocation
    from mutate4py._source_loading import _finalize_source

    src_path = str(tmp_path / "f.py")
    with open(src_path, "w") as f:
        f.write(SRC)
    existing = reconcile_manifest(None, build_manifest(SRC, tested_at=TESTED_AT), _SCORES, fingerprint="fp-old")

    _finalize_source(
        SRC,
        TESTED_LATER,
        src_path + ".bak",
        ManifestLocation(path=src_path),
        existing_manifest=existing,
        scored_run=_ScoredNothingStub(),
        fingerprint="fp-new",
    )

    assert _footer_tests_fingerprint(src_path) == "fp-new"


@pytest.mark.unit
def test_run_setup_fingerprints_the_tests_the_run_will_measure(tmp_path):
    from mutate4py._source_loading import _prepare_run_setup

    (tmp_path / "tests").mkdir()
    test_file = tmp_path / "tests" / "test_calc.py"
    test_file.write_text("def test_f():\n    assert True\n")
    src_path = str(tmp_path / "f.py")
    with open(src_path, "w") as f:
        f.write(SRC)

    first = _prepare_run_setup(
        path=src_path, source=SRC, manifest_file=False, cwd=str(tmp_path), pytest_args=["tests"]
    ).fingerprint
    test_file.write_text("def test_f():\n    assert 1 == 1\n")
    second = _prepare_run_setup(
        path=src_path, source=SRC, manifest_file=False, cwd=str(tmp_path), pytest_args=["tests"]
    ).fingerprint

    assert first != second


def _sidecar_tests_fingerprint(src_path):
    import json

    with open(src_path + ".manifest.json") as f:
        return json.load(f).get("tests_fingerprint")


@pytest.mark.unit
def test_update_manifest_keeps_the_stored_fingerprint_when_it_rewrites_the_sidecar(tmp_path):
    from mutate4py._manifest import reconcile_manifest
    from mutate4py._manifest_modes import update_manifest
    from mutate4py._manifest_storage import write_sidecar_manifest

    src_path = str(tmp_path / "f.py")
    existing = reconcile_manifest(None, build_manifest(SRC, tested_at=TESTED_AT), _SCORES, fingerprint="fp-old")
    write_sidecar_manifest(src_path, existing)
    changed = SRC.replace("a > b", "a >= b")

    assert update_manifest(path=src_path, source=changed, manifest_file=True) == 0

    assert _sidecar_tests_fingerprint(src_path) == "fp-old"


@pytest.mark.unit
@pytest.mark.parametrize("stored", [None, "fp-old"])
def test_check_manifest_passes_an_unchanged_source_whatever_the_stored_fingerprint(tmp_path, stored):
    from mutate4py._manifest_modes import check_manifest
    from mutate4py._manifest_storage import write_sidecar_manifest

    src_path = str(tmp_path / "f.py")
    manifest = build_manifest(SRC, tested_at=TESTED_AT)
    if stored is not None:
        manifest["tests_fingerprint"] = stored
    write_sidecar_manifest(src_path, manifest)

    assert check_manifest(path=src_path, source=SRC, manifest_file=True) == 0
