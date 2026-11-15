"""Source loading for the run loop: backup rescue, manifest diffing against the
prior run, and site discovery on the stripped source — everything that must
happen before coverage acquisition and site selection can start.
"""

import dataclasses
import datetime
import logging
import os
import shlex
from typing import NamedTuple

from mutate4py._digest_changes import functions_with_changed_digest
from mutate4py._discovery import Site, discover_sites
from mutate4py._equivalent import marker_lines
from mutate4py._manifest import (
    build_manifest,
    diff_manifests,
    functions_with_survivors,
    functions_with_unmarked_acceptances,
    reconcile_manifest,
    strip_manifest,
)
from mutate4py._manifest_storage import (
    ManifestLocation,
    _read_existing_manifest,
    _write_manifest_output,
)
from mutate4py._scoring import ScoredRun
from mutate4py._tests_fingerprint import tests_fingerprint
from mutate4py._unscored import unscored_functions

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


class ManifestDiff(NamedTuple):
    """What `_compute_manifest_diff` found: the stripped source, the stored Manifest and the changed functions."""

    clean_source: str
    existing_manifest: dict | None
    manifest_exists: bool
    changed_fn_ids: set[str]
    tested_at: str


def _compute_manifest_diff(source: str, loc: ManifestLocation) -> ManifestDiff:
    """Strip manifest, discover sites, diff.

    changed_fn_ids also holds every function with recorded survivors and no tests
    digest: such a function is not current, so the next default run retries it
    even when its hash is unchanged. It also holds every function whose accepted
    survivor lost its marker, and every Unscored function (ADR 0029 rule 1), which a
    default run scores. The "Changed mutation sites" count includes those Sites too.
    A run scores a changed function even when no covered Site reaches it. Functions whose
    stored tests digest changed join changed_fn_ids later, once the Measurement has run
    (apply_digest_changes).
    """
    clean_source = strip_manifest(source)
    existing_manifest, manifest_exists = _read_existing_manifest(source, loc)
    tested_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    current_manifest = build_manifest(clean_source, tested_at=tested_at)
    changed_fn_ids = (
        diff_manifests(existing_manifest, current_manifest)
        | functions_with_survivors(existing_manifest)
        | functions_with_unmarked_acceptances(existing_manifest, current_manifest, marker_lines(clean_source))
        | unscored_functions(existing_manifest, current_manifest)
    )
    return ManifestDiff(clean_source, existing_manifest, manifest_exists, changed_fn_ids, tested_at)


def _finalize_source(  # noqa: PLR0913 - keeps the positional contract tests/test_source_loading.py relies on
    clean_source: str,
    tested_at: str,
    bak_path: str,
    loc: ManifestLocation,
    *,
    existing_manifest: dict | None = None,
    scored_run: ScoredRun | None = None,
    fresh_digests: dict[str, str] | None = None,
    fingerprint: str | None = None,
) -> dict:
    # Unlike update_manifest, the write can't be skipped outright: a run with
    # selected sites leaves the last-tested mutant on disk (the per-site loop
    # never reverts), so clean_source must always be restored. Only the
    # manifest choice is conditional — reusing existing_manifest keeps the
    # written bytes identical to what's already on disk when nothing changed.
    candidate_manifest = build_manifest(clean_source, tested_at=tested_at)
    scores = None
    if scored_run is not None:
        scores = scored_run.function_scores([fn["id"] for fn in candidate_manifest["functions"]])
    # Every completed scored run records the fingerprint it measured, even one that wrote no score block (spec 5b).
    # A run with no scored run (an errored one, or an unscored caller) keeps the stored one.
    recorded = fingerprint if scored_run is not None else None
    manifest_to_embed = reconcile_manifest(
        existing_manifest, candidate_manifest, scores, fresh_digests=fresh_digests, fingerprint=recorded
    )
    _write_manifest_output(clean_source, manifest_to_embed, loc)
    if os.path.isfile(bak_path):
        os.remove(bak_path)
    return manifest_to_embed


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
    diff = _compute_manifest_diff(source, loc)
    all_sites = discover_sites(diff.clean_source)
    return LoadedSource(
        clean_source=diff.clean_source,
        existing_manifest=diff.existing_manifest,
        manifest_exists=diff.manifest_exists,
        changed_fn_ids=diff.changed_fn_ids,
        tested_at=diff.tested_at,
        all_sites=all_sites,
        changed_count=_changed_site_count(all_sites, diff.changed_fn_ids),
    )


def _changed_site_count(all_sites: list[Site], changed_fn_ids: set[str]) -> int:
    """How many Sites belong to a changed function."""
    return len([s for s in all_sites if s.function_id in changed_fn_ids])


def apply_digest_changes(loaded: LoadedSource, fresh_digests: dict[str, str]) -> None:
    """Add the functions whose stored tests digest this run's Measurement no longer matches (#106).

    Called after the Measurement and before any Site is selected, so the added functions are
    selected like any changed function. The changed Site count is updated to match.
    """
    changed = functions_with_changed_digest(loaded.existing_manifest, fresh_digests)
    if not changed:
        return
    loaded.changed_fn_ids |= changed
    loaded.changed_count = _changed_site_count(loaded.all_sites, loaded.changed_fn_ids)


@dataclasses.dataclass
class RunSetup:
    """Paths, loaded source state and the run's tests fingerprint, established before coverage/selection."""

    bak_path: str
    loc: ManifestLocation
    loaded: LoadedSource
    fingerprint: str


def _prepare_run_setup(*, path: str, source: str, manifest_file: bool, cwd: str, pytest_args: list[str]) -> RunSetup:
    source_dir = os.path.dirname(os.path.abspath(path))
    bak_path = os.path.join(source_dir, os.path.basename(path) + ".bak")
    loc = ManifestLocation(path=path, manifest_file=manifest_file)
    loaded = _load_clean_source(bak_path, source, loc)
    # After the backup restore, and before any Mutant is written: the fingerprint reads the source as it is restored.
    fingerprint = tests_fingerprint(cwd, shlex.join(pytest_args))
    return RunSetup(bak_path=bak_path, loc=loc, loaded=loaded, fingerprint=fingerprint)
