"""Which functions a run scores because no stored score block covers them (ADR 0029 rule 1, spec #115).

Split from `_manifest.py`, which sits at its size cap (tests/test_module_size_guard.py). It reads each
entry's score block through the same `_scored_fields` `_manifest` reads, so it agrees with `is_unscored`.
"""

from mutate4py._manifest import _scored_fields


def unscored_functions(existing: dict | None, current: dict) -> set[str]:
    """Ids of current functions with no stored score block (ADR 0029 rule 1).

    That covers a function the stored Manifest never scored, such as one a 0.1.4 Manifest holds, and a
    function the stored Manifest does not hold at all. None gives an empty set: with no Manifest the run
    is a full-file run, which scores every function anyway.
    """
    if existing is None:
        return set()
    scored = {fn["id"] for fn in existing["functions"] if _scored_fields(fn) is not None}
    return {fn["id"] for fn in current["functions"]} - scored
