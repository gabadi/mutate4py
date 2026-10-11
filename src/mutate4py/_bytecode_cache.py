"""Removes a guarded file's stale compiled bytecode before a mutant run."""

import importlib.util
import os

__all__ = ["invalidate_bytecode_cache"]


def invalidate_bytecode_cache(guarded_path: str) -> None:
    """Remove any compiled-bytecode cache for guarded_path, if present."""
    try:
        cached = importlib.util.cache_from_source(guarded_path)
    except ValueError:
        return
    try:
        os.remove(cached)
    except FileNotFoundError:
        pass
