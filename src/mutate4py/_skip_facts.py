"""The stored Manifests an invocation reads to decide whether it may skip its Measurement (design 89 §5b).

`skipped_manifests` reads every target of one invocation and reduces each stored Manifest to the facts
`can_skip_measurement` decides from. It returns the Manifests when the whole invocation may skip, else None.
A target that cannot be read or parsed, has no Manifest, or sits beside a `.bak` left by an interrupted run
makes the invocation unskippable.
"""

import dataclasses
import os
import shlex

from mutate4py._equivalent import marker_lines
from mutate4py._manifest import (
    build_manifest,
    extract_manifest,
    functions_with_unmarked_acceptances,
    is_unscored,
    source_sha256,
    strip_manifest,
)
from mutate4py._manifest_storage import read_sidecar_manifest
from mutate4py._tests_fingerprint import TargetFacts, can_skip_measurement, tests_fingerprint


@dataclasses.dataclass(frozen=True)
class _Reading:
    """One target's stored Manifest and the facts the skip decision reads from it."""

    manifest: dict
    facts: TargetFacts


def _facts_for(manifest: dict, clean: str) -> TargetFacts:
    current = build_manifest(clean, tested_at="")
    return TargetFacts(
        manifest_fingerprint=manifest.get("tests_fingerprint"),
        source_unchanged=manifest.get("source_sha256") == source_sha256(clean),
        fully_scored=not is_unscored(manifest)
        and all(fn.get("tests_digest") is not None for fn in manifest["functions"]),
        accepted_markers_intact=not functions_with_unmarked_acceptances(manifest, current, marker_lines(clean)),
    )


def _read_target(path: str, *, manifest_file: bool) -> _Reading | None:
    """One target's reading; None when it has no Manifest, cannot be read or parsed, or a `.bak` is present."""
    if os.path.isfile(path + ".bak"):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        if manifest_file:
            manifest, _ = read_sidecar_manifest(path)
        else:
            manifest, _ = extract_manifest(source)
        if manifest is None:
            return None
        return _Reading(manifest, _facts_for(manifest, strip_manifest(source)))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return None


def skipped_manifests(
    files: list[str],
    pytest_args: list[str],
    cwd: str,
    *,
    manifest_file: bool,
) -> list[dict] | None:
    """The stored Manifest of every target when the invocation may skip its Measurement, else None.

    Decided once for the whole invocation: any target that blocks the skip blocks it for all of them.
    """
    readings: list[_Reading] = []
    for path in files:
        reading = _read_target(path, manifest_file=manifest_file)
        if reading is None:
            return None
        readings.append(reading)
    fresh = tests_fingerprint(cwd, shlex.join(pytest_args))
    if not can_skip_measurement([r.facts for r in readings], fresh):
        return None
    return [r.manifest for r in readings]
