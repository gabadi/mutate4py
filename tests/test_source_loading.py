"""Unit tests for run-loop source loading (_source_loading.py)."""

import os

from mutate4py._manifest_storage import ManifestLocation
from mutate4py._source_loading import _finalize_source
import pytest


# ── _finalize_source manifest content ────────────────────────────────────────


@pytest.mark.unit
def test_finalize_source_embeds_manifest_with_tested_at(tmp_path):
    """_finalize_source writes the file with a manifest containing the tested_at timestamp."""
    import json

    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "f.py")
    bak_path = src_path + ".bak"
    with open(src_path, "w") as f:
        f.write(src)

    tested_at = "2026-01-01T00:00:00Z"
    _finalize_source(src, tested_at, bak_path, ManifestLocation(path=src_path))

    with open(src_path) as f:
        content = f.read()

    assert "mutate4py-manifest-begin" in content
    manifest_line = [ln for ln in content.splitlines() if ln.startswith("# {")][0]
    manifest = json.loads(manifest_line[2:])
    assert manifest["tested_at"] == tested_at


@pytest.mark.unit
def test_finalize_source_removes_bak_when_present(tmp_path):
    """_finalize_source removes the .bak file if it exists after writing."""
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "f.py")
    bak_path = src_path + ".bak"
    with open(src_path, "w") as f:
        f.write(src)
    with open(bak_path, "w") as f:
        f.write(src)

    _finalize_source(src, "2026-01-01T00:00:00Z", bak_path, ManifestLocation(path=src_path))

    assert not os.path.isfile(bak_path)


@pytest.mark.unit
def test_finalize_source_manifest_is_valid_dict(tmp_path):
    """The embedded manifest is valid JSON dict (not null, not a string)."""
    import json

    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "f.py")
    bak_path = src_path + ".bak"
    with open(src_path, "w") as f:
        f.write(src)

    _finalize_source(src, "2026-01-01T00:00:00Z", bak_path, ManifestLocation(path=src_path))

    with open(src_path) as f:
        content = f.read()

    manifest_line = [ln for ln in content.splitlines() if ln.startswith("# {")][0]
    manifest = json.loads(manifest_line[2:])
    assert isinstance(manifest, dict)
    assert "sites" in manifest or "ast_hash" in manifest or "tested_at" in manifest


@pytest.mark.unit
def test_finalize_source_sidecar_writes_manifest_file_not_footer(tmp_path):
    """manifest_file=True => sidecar JSON gets the manifest; source stays footer-free."""
    import json

    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "f.py")
    bak_path = src_path + ".bak"
    with open(src_path, "w") as f:
        f.write(src)
    sidecar_path = src_path + ".manifest.json"

    _finalize_source(src, "2026-01-01T00:00:00Z", bak_path, ManifestLocation(path=src_path, manifest_file=True))

    with open(src_path) as f:
        content = f.read()
    assert content == src
    assert "mutate4py-manifest-begin" not in content

    with open(sidecar_path) as f:
        sidecar = json.load(f)
    assert sidecar["tested_at"] == "2026-01-01T00:00:00Z"
    assert sidecar["functions"][0]["id"] == "func/f"


@pytest.mark.unit
def test_finalize_source_sidecar_removes_bak_when_present(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "f.py")
    bak_path = src_path + ".bak"
    with open(src_path, "w") as f:
        f.write(src)
    with open(bak_path, "w") as f:
        f.write(src)

    _finalize_source(src, "2026-01-01T00:00:00Z", bak_path, ManifestLocation(path=src_path, manifest_file=True))

    assert not os.path.isfile(bak_path)


@pytest.mark.unit
def test_finalize_source_retains_existing_manifest_when_structurally_equal(tmp_path):
    """When existing_manifest matches the candidate built from clean_source, the OLD
    tested_at is kept in the written file rather than being bumped to the new one."""
    import json

    from mutate4py._manifest import build_manifest

    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "f.py")
    bak_path = src_path + ".bak"
    with open(src_path, "w") as f:
        f.write(src)

    old_tested_at = "2020-01-01T00:00:00Z"
    existing_manifest = build_manifest(src, tested_at=old_tested_at)

    _finalize_source(
        src,
        "2026-01-01T00:00:00Z",
        bak_path,
        ManifestLocation(path=src_path),
        existing_manifest=existing_manifest,
    )

    with open(src_path) as f:
        content = f.read()
    manifest_line = [ln for ln in content.splitlines() if ln.startswith("# {")][0]
    manifest = json.loads(manifest_line[2:])
    assert manifest["tested_at"] == old_tested_at


@pytest.mark.unit
def test_finalize_source_bumps_tested_at_when_existing_manifest_differs(tmp_path):
    """When existing_manifest is structurally different from the candidate, a fresh
    manifest with the new tested_at is embedded (today's default behavior)."""
    import json

    from mutate4py._manifest import build_manifest

    old_src = "def f(a, b):\n    return a > b\n"
    new_src = "def f(a, b):\n    return a >= b\n"
    src_path = str(tmp_path / "f.py")
    bak_path = src_path + ".bak"
    with open(src_path, "w") as f:
        f.write(new_src)

    old_tested_at = "2020-01-01T00:00:00Z"
    existing_manifest = build_manifest(old_src, tested_at=old_tested_at)
    new_tested_at = "2026-01-01T00:00:00Z"

    _finalize_source(
        new_src,
        new_tested_at,
        bak_path,
        ManifestLocation(path=src_path),
        existing_manifest=existing_manifest,
    )

    with open(src_path) as f:
        content = f.read()
    manifest_line = [ln for ln in content.splitlines() if ln.startswith("# {")][0]
    manifest = json.loads(manifest_line[2:])
    assert manifest["tested_at"] == new_tested_at
