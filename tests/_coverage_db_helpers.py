"""Shared helpers for tests that exercise the --build-test-contexts staleness
cache (_test_context_cache.py) and the orchestration around it — both need to
lay out a small project tree and stand in a coverage db that only has to be
shaped enough for the cache to read it.
"""

import sqlite3
from collections.abc import Iterable

__all__ = ["make_coverage_db", "write_text"]


def write_text(path, text: str) -> None:
    """Write text to path (accepts a str or a Path)."""
    with open(path, "w") as f:
        f.write(text)


def make_coverage_db(db_path, paths: Iterable[str]) -> None:
    """A minimal sqlite db shaped enough like coverage.py's `file` table for
    _test_context_cache's `SELECT path FROM file` to work against."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE file (id INTEGER PRIMARY KEY, path TEXT)")
        conn.executemany("INSERT INTO file (path) VALUES (?)", [(p,) for p in paths])
        conn.commit()
    finally:
        conn.close()
