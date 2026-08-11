"""Walking a project tree for its first-party Python files.

Two walks in this project need the same answer to "which subdirectories hold
code this project wrote": target resolution, deciding what to mutate
(`_target_resolution.py`), and the --build-test-contexts staleness cache,
deciding what to fingerprint (`_test_context_cache.py`). They sit in different
layers and must not import each other, so the shared predicate lives here in
`primitives` where both reach it for free (see tach.toml's header).
"""

__all__ = ["PRUNED_DIR_NAMES", "walkable_dirs"]

PRUNED_DIR_NAMES = {"__pycache__", "venv", "node_modules"}


def walkable_dirs(dirs: list[str]) -> list[str]:
    """Sorted subdirectories to descend into.

    Prunes __pycache__, venv, node_modules, and any dot-directory (e.g.
    .git, .venv). build/ and dist/ are deliberately left walkable.
    """
    return sorted(d for d in dirs if d not in PRUNED_DIR_NAMES and not d.startswith("."))
