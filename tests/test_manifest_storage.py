"""Unit tests for the manifest storage adapters (_manifest_storage.py)."""

from mutate4py._manifest_storage import read_sidecar_manifest, write_sidecar_manifest
import pytest


# ── read_sidecar_manifest / write_sidecar_manifest (sidecar file IO) ──────────


@pytest.mark.unit
def test_read_sidecar_manifest_missing_file_returns_none_false(tmp_path):
    p = tmp_path / "mod.py"
    assert read_sidecar_manifest(str(p)) == (None, False)


@pytest.mark.unit
def test_read_sidecar_manifest_invalid_json_returns_none_false(tmp_path):
    p = tmp_path / "mod.py"
    (tmp_path / "mod.py.manifest.json").write_text("not-json")
    assert read_sidecar_manifest(str(p)) == (None, False)


@pytest.mark.unit
def test_read_sidecar_manifest_non_dict_json_returns_none_false(tmp_path):
    """Valid JSON that isn't an object (e.g. a hand-corrupted sidecar) must not
    be treated as a real manifest — it should read as missing so the next
    --update-manifest overwrites it with a fresh one."""
    p = tmp_path / "mod.py"
    (tmp_path / "mod.py.manifest.json").write_text("[1, 2, 3]")
    assert read_sidecar_manifest(str(p)) == (None, False)


@pytest.mark.unit
def test_write_sidecar_manifest_round_trips_through_read(tmp_path):
    p = tmp_path / "mod.py"
    m = {
        "version": 1,
        "tested_at": "2026-01-01T00:00:00Z",
        "module_hash": "abc",
        "functions": [],
    }
    write_sidecar_manifest(str(p), m)
    result, ok = read_sidecar_manifest(str(p))
    assert ok is True
    assert result == m


@pytest.mark.unit
def test_write_sidecar_manifest_overwrites_previous_content(tmp_path):
    p = tmp_path / "mod.py"
    write_sidecar_manifest(
        str(p),
        {"version": 1, "tested_at": "x", "module_hash": "old", "functions": []},
    )
    write_sidecar_manifest(
        str(p),
        {"version": 1, "tested_at": "x", "module_hash": "new", "functions": []},
    )
    result, _ = read_sidecar_manifest(str(p))
    assert result["module_hash"] == "new"


@pytest.mark.unit
def test_write_sidecar_manifest_uses_source_path_plus_suffix(tmp_path):
    p = tmp_path / "mod.py"
    write_sidecar_manifest(
        str(p),
        {"version": 1, "tested_at": "x", "module_hash": "abc", "functions": []},
    )
    assert (tmp_path / "mod.py.manifest.json").is_file()


@pytest.mark.unit
def test_write_sidecar_manifest_does_not_touch_other_files_sidecars(tmp_path):
    p_a = tmp_path / "a.py"
    p_b = tmp_path / "b.py"
    write_sidecar_manifest(
        str(p_a),
        {"version": 1, "tested_at": "x", "module_hash": "a-hash", "functions": []},
    )
    write_sidecar_manifest(
        str(p_b),
        {"version": 1, "tested_at": "x", "module_hash": "b-hash", "functions": []},
    )
    result_a, ok_a = read_sidecar_manifest(str(p_a))
    result_b, ok_b = read_sidecar_manifest(str(p_b))
    assert ok_a is True
    assert ok_b is True
    assert result_a["module_hash"] == "a-hash"
    assert result_b["module_hash"] == "b-hash"
