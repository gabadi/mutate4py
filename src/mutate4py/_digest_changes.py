"""Which functions a run's fresh tests digests change (#106).

Split from `_manifest.py`, which sits at its size cap. It reads each entry's stored digest
through the same score block `_manifest` reads, so an unscored entry is never a digest change.
"""

from mutate4py._manifest import _scored_fields


def _stored_digests(manifest: dict | None) -> dict[str, str]:
    """The tests digest of every entry that has one, by function id."""
    if manifest is None:
        return {}
    scored = {fn["id"]: _scored_fields(fn) or {} for fn in manifest["functions"]}
    return {fid: f["tests_digest"] for fid, f in scored.items() if "tests_digest" in f}


def functions_with_changed_digest(manifest: dict | None, fresh_digests: dict[str, str]) -> set[str]:
    """Ids of functions whose stored tests digest differs from this run's fresh one (#106).

    An entry with no stored digest is adoption, not a change, and a function with no fresh digest
    is left alone. None gives an empty set.
    """
    return {fid for fid, stored in _stored_digests(manifest).items() if fresh_digests.get(fid, stored) != stored}
