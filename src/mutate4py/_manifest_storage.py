"""Manifest storage adapters for the run loop: sidecar JSON (--manifest-file)
vs. the embedded source footer, behind one read-by-location / write-by-location
interface. `_manifest.py` owns the manifest *format*; this module owns
manifest *storage* — where a manifest lives and how it's read/written, not
what reconciling two manifests means (that stays in `_runner.py`, alongside
the one caller that decides it).
"""

import dataclasses

from mutate4py._manifest import embed_manifest, extract_manifest
from mutate4py._sidecar_io import read_json_sidecar, write_json_sidecar

__all__ = [
    "ManifestLocation",
    "read_sidecar_manifest",
    "write_sidecar_manifest",
]


@dataclasses.dataclass(frozen=True)
class ManifestLocation:
    """Where a source file's manifest lives: sidecar JSON alongside it, or an embedded footer."""

    path: str
    manifest_file: bool = False


def _sidecar_path(source_path: str) -> str:
    """Return the sidecar manifest path for a source file: <source_path>.manifest.json."""
    return source_path + ".manifest.json"


def read_sidecar_manifest(source_path: str) -> tuple[dict | None, bool]:
    """Read source_path's manifest from its own sidecar JSON file.

    Missing sidecar, parse failure, or valid-but-non-dict JSON => (None, False),
    never an error (mirrors extract_manifest).
    """
    return read_json_sidecar(_sidecar_path(source_path))


def write_sidecar_manifest(source_path: str, manifest: dict) -> None:
    """Write source_path's manifest to its own sidecar JSON file."""
    write_json_sidecar(_sidecar_path(source_path), manifest)


def _read_existing_manifest(source: str, loc: ManifestLocation) -> tuple[dict | None, bool]:
    """Read the prior manifest from its configured storage (sidecar or in-source footer)."""
    if loc.manifest_file:
        return read_sidecar_manifest(loc.path)
    return extract_manifest(source)


def _write_manifest_output(
    clean_source: str,
    manifest: dict,
    loc: ManifestLocation,
    *,
    write_source: bool = True,
    write_manifest: bool = True,
) -> None:
    """Write clean_source/manifest to their configured storage (sidecar or in-source footer).

    In embed mode (loc.manifest_file is False) source and footer are always written
    together as one file, so write_source/write_manifest are ignored there.
    """
    if loc.manifest_file:
        if write_source:
            with open(loc.path, "w") as f:
                f.write(clean_source)
        if write_manifest:
            write_sidecar_manifest(loc.path, manifest)
    else:
        with open(loc.path, "w") as f:
            f.write(embed_manifest(clean_source, manifest))
