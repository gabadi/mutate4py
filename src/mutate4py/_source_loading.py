"""Source loading for the run loop: backup rescue, manifest diffing against the
prior run, and site discovery on the stripped source — everything that must
happen before coverage acquisition and site selection can start.
"""

import dataclasses
import datetime
import logging
import os

from mutate4py._discovery import Site, discover_sites
from mutate4py._manifest import (
    build_manifest,
    diff_manifests,
    reconcile_manifest,
    strip_manifest,
)
from mutate4py._manifest_storage import (
    ManifestLocation,
    _read_existing_manifest,
    _write_manifest_output,
)

_logger = logging.getLogger(__name__)


def _restore_from_backup(path: str, bak_path: str) -> str | None:
    """Restore source from backup if present; return rescued source or None."""
    if not os.path.isfile(bak_path):
        return None
    with open(bak_path) as f:
        rescued = f.read()
    with open(path, "w") as f:
        f.write(rescued)
    _logger.info("Restored source from backup (previous run was interrupted).")
    with open(path) as f:
        return f.read()


def _compute_manifest_diff(source: str, loc: ManifestLocation) -> tuple[str, dict | None, bool, set[str], str]:
    """Strip manifest, discover sites, diff.

    Returns (clean_source, existing_manifest, manifest_exists, changed_fn_ids, tested_at).
    """
    clean_source = strip_manifest(source)
    existing_manifest, manifest_exists = _read_existing_manifest(source, loc)
    tested_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    current_manifest = build_manifest(clean_source, tested_at=tested_at)
    changed_fn_ids = diff_manifests(existing_manifest, current_manifest)
    return clean_source, existing_manifest, manifest_exists, changed_fn_ids, tested_at


def _finalize_source(
    clean_source: str,
    tested_at: str,
    bak_path: str,
    loc: ManifestLocation,
    *,
    existing_manifest: dict | None = None,
) -> None:
    # Unlike update_manifest, the write can't be skipped outright: a run with
    # selected sites leaves the last-tested mutant on disk (the per-site loop
    # never reverts), so clean_source must always be restored. Only the
    # manifest choice is conditional — reusing existing_manifest keeps the
    # written bytes identical to what's already on disk when nothing changed.
    candidate_manifest = build_manifest(clean_source, tested_at=tested_at)
    manifest_to_embed = reconcile_manifest(existing_manifest, candidate_manifest)
    _write_manifest_output(clean_source, manifest_to_embed, loc)
    if os.path.isfile(bak_path):
        os.remove(bak_path)


@dataclasses.dataclass
class LoadedSource:
    """The stripped source plus everything diffed against its prior manifest."""

    clean_source: str
    existing_manifest: dict | None
    manifest_exists: bool
    changed_fn_ids: set[str]
    tested_at: str
    all_sites: list[Site]
    changed_count: int


def _load_clean_source(bak_path: str, source: str, loc: ManifestLocation) -> LoadedSource:
    """Rescue from backup if needed, strip/diff the manifest, and discover sites."""
    rescued = _restore_from_backup(loc.path, bak_path)
    if rescued is not None:
        source = rescued
    (
        clean_source,
        existing_manifest,
        manifest_exists,
        changed_fn_ids,
        tested_at,
    ) = _compute_manifest_diff(source, loc)
    all_sites = discover_sites(clean_source)
    changed_count = len([s for s in all_sites if s.function_id in changed_fn_ids])
    return LoadedSource(
        clean_source=clean_source,
        existing_manifest=existing_manifest,
        manifest_exists=manifest_exists,
        changed_fn_ids=changed_fn_ids,
        tested_at=tested_at,
        all_sites=all_sites,
        changed_count=changed_count,
    )


@dataclasses.dataclass
class RunSetup:
    """Paths and loaded source state established before coverage/selection."""

    bak_path: str
    loc: ManifestLocation
    loaded: LoadedSource


def _prepare_run_setup(*, path: str, source: str, manifest_file: bool) -> RunSetup:
    source_dir = os.path.dirname(os.path.abspath(path))
    bak_path = os.path.join(source_dir, os.path.basename(path) + ".bak")
    loc = ManifestLocation(path=path, manifest_file=manifest_file)
    loaded = _load_clean_source(bak_path, source, loc)
    return RunSetup(bak_path=bak_path, loc=loc, loaded=loaded)
