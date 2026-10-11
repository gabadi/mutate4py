"""The two no-run Manifest modes: --update-manifest and --check-manifest."""

import datetime
import logging

from mutate4py._equivalent import marker_lines
from mutate4py._manifest import (
    build_manifest,
    functions_with_unmarked_acceptances,
    has_accepted_survivors,
    is_unscored,
    manifests_structurally_equal,
    reconcile_manifest,
    recorded_survivors,
    source_sha256,
    strip_manifest,
)
from mutate4py._manifest_storage import (
    ManifestLocation,
    _read_existing_manifest,
    _write_manifest_output,
)

_logger = logging.getLogger(__name__)


def update_manifest(*, path: str, source: str, manifest_file: bool = False) -> int:
    """Execute --update-manifest: refresh the manifest in its configured storage. Returns exit code."""
    loc = ManifestLocation(path=path, manifest_file=manifest_file)
    existing, _ = _read_existing_manifest(source, loc)
    clean = strip_manifest(source)
    tested_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    candidate = build_manifest(clean, tested_at=tested_at)
    manifest_to_embed = reconcile_manifest(existing, candidate)
    manifest_changed = manifest_to_embed is not existing

    if manifest_file:
        source_has_stale_footer = clean != source
        if not manifest_changed and not source_has_stale_footer:
            _logger.info(f"Manifest unchanged: {path}")
            return 0
        _write_manifest_output(
            clean,
            manifest_to_embed,
            loc,
            write_source=source_has_stale_footer,
            write_manifest=manifest_changed,
        )
        _logger.info(f"Updated manifest: {path}")
        return 0

    if not manifest_changed:
        _logger.info(f"Manifest unchanged: {path}")
        return 0
    _write_manifest_output(clean, manifest_to_embed, loc)
    _logger.info(f"Updated manifest: {path}")
    return 0


def check_manifest(*, path: str, source: str, manifest_file: bool = False) -> int:
    """Check if the manifest in its configured storage is up to date. Returns 0 if current, 1 if stale or missing."""
    clean = strip_manifest(source)
    loc = ManifestLocation(path=path, manifest_file=manifest_file)
    existing, manifest_exists = _read_existing_manifest(source, loc)
    if not manifest_exists:
        _logger.info(f"Manifest missing: {path}")
        return 1
    # A recorded survivor fails before the fast path: a matching source_sha256
    # must not hide a function the last scored run left surviving.
    if _report_survivors(path, existing):
        return 1
    suffix = " (unscored)" if is_unscored(existing) else ""
    if _fast_path_current(existing, clean):
        _logger.info(f"Manifest current: {path}{suffix}")
        return 0
    tested_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    candidate = build_manifest(clean, tested_at=tested_at)
    if _report_unmarked(path, existing, candidate, clean):
        return 1
    return _verdict(path, existing, candidate, clean, suffix)


def _fast_path_current(existing: dict, clean: str) -> bool:
    """True when the stored source_sha256 matches and no accepted survivor needs the marker check.

    A matching source_sha256 cannot vouch for an accepted survivor: update_manifest
    rewrites the sha while keeping the reason, even when the marker is gone. Only
    manifests with accepted survivors leave the fast path, so the rest stay parse-free.
    """
    return _source_unchanged(existing, clean) and not has_accepted_survivors(existing)


def _report_unmarked(path: str, existing: dict, candidate: dict, clean: str) -> bool:
    """Log each function whose accepted survivor lost its marker and return True when there are any."""
    unmarked = functions_with_unmarked_acceptances(existing, candidate, marker_lines(clean))
    if not unmarked:
        return False
    _logger.info(f"Manifest stale: {path}")
    for fid in sorted(unmarked):
        _logger.info(f"  {fid}: an accepted survivor's equivalent marker was removed or changed")
    return True


def _verdict(path: str, existing: dict, candidate: dict, clean: str, suffix: str) -> int:
    """Return 0 and log current when the parsed manifest matches the source, else log stale and return 1."""
    if manifests_structurally_equal(existing, candidate) or _source_unchanged(existing, clean):
        _logger.info(f"Manifest current: {path}{suffix}")
        return 0
    _logger.info(f"Manifest stale: {path}")
    return 1


def _report_survivors(path: str, existing: dict) -> bool:
    """Log each recorded survivor on its own line and return True when there are any."""
    survivors = recorded_survivors(existing)
    if not survivors:
        return False
    lines = [f"Manifest has survivors: {path}"]
    lines += [f"  line {s['line']} {s['desc']} {fid}" for fid, s in survivors]
    _logger.info("\n".join(lines))
    return True


def _source_unchanged(existing: dict, clean: str) -> bool:
    """True when the stored source_sha256 matches the stripped source (the fast path)."""
    existing_sha = existing.get("source_sha256")
    return existing_sha is not None and existing_sha == source_sha256(clean)
