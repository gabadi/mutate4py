"""Per-mutant test selection from a coverage.py SQLite context database."""

import sqlite3
import threading

__all__ = [
    "TestContextDB",
    "TestContextError",
    "_classify",
    "_numbits_to_lines",
    "_strip_context_suffix",
]


class TestContextError(Exception):
    pass


def _numbits_to_lines(numbits: bytes) -> set[int]:
    """Decode a coverage.py numbits blob into a set of 1-based line numbers.

    byte N bit B → line N*8 + B + 1 (coverage.py internal format, stable v7+).
    """
    lines: set[int] = set()
    for byte_idx, byte_val in enumerate(numbits):
        for bit_idx in range(8):
            if byte_val & (1 << bit_idx):
                lines.add(byte_idx * 8 + bit_idx + 1)
    return lines


def _classify(tests: list[str], *, static: bool) -> tuple[str, list[str]]:
    """Fold a line's matched contexts into an outcome (see `tests_for_line`)."""
    if tests:
        return "narrowed", tests
    if static:
        return "static", []
    return "line-absent", []


def _strip_context_suffix(context: str) -> str:
    """Strip the |<suffix> from a coverage.py context string to get the pytest node ID."""
    if "|" in context:
        return context.rsplit("|", 1)[0]
    return context


class TestContextDB:
    """Read-only view of a .coverage SQLite context database."""

    def __init__(self, db_path: str) -> None:
        # check_same_thread=False + _lock: parallel Worker dispatch shares one
        # TestContextDB across worker threads, so sqlite3's default
        # same-thread guard must be relaxed and access serialized instead.
        try:
            self._conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
        except sqlite3.OperationalError as e:
            raise TestContextError(f"cannot open coverage db: {e}") from e
        self._lock = threading.Lock()
        cur = self._conn.cursor()
        cur.execute("SELECT value FROM meta WHERE key = 'has_arcs'")
        row = cur.fetchone()
        self._has_arcs = bool(row and int(row[0]))

    def tests_for_line(self, source_path: str, line: int) -> tuple[str, list[str]]:
        """Classify (source_path, line) against the db; return (outcome, node_ids).

        Outcome is one of:
          "narrowed"    — node_ids are the pytest node IDs covering the line
          "static"      — the line ran only under the empty (whole-run) context,
                          i.e. at import time, so no single test owns it
          "line-absent" — the file is in the db but no context recorded the line
          "file-absent" — the file is not in the db at all
        node_ids is empty for every outcome but "narrowed".
        """
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT id FROM file WHERE path = ?", (source_path,))
            row = cur.fetchone()
            if row is None:
                return "file-absent", []
            file_id = row[0]
            if self._has_arcs:
                return self._tests_for_line_arcs(cur, file_id, line)
            return self._tests_for_line_bits(cur, file_id, line)

    def _tests_for_line_bits(self, cur: sqlite3.Cursor, file_id: int, line: int) -> tuple[str, list[str]]:
        cur.execute(
            "SELECT c.context, lb.numbits FROM line_bits lb "
            "JOIN context c ON c.id = lb.context_id "
            "WHERE lb.file_id = ?",
            (file_id,),
        )
        tests: list[str] = []
        static = False
        for ctx_str, numbits in cur.fetchall():
            if line not in _numbits_to_lines(numbits):
                continue
            if ctx_str:
                tests.append(_strip_context_suffix(ctx_str))
            else:
                static = True
        return _classify(tests, static=static)

    def _tests_for_line_arcs(self, cur: sqlite3.Cursor, file_id: int, line: int) -> tuple[str, list[str]]:
        """Branch-coverage mode: derive covering tests from the `arc` table.

        Mirrors coverage.py's own `SqliteDb.contexts_by_lineno`: a context
        "touches" a line if that line appears as either endpoint of an arc it
        recorded, provided the endpoint is positive. Negative fromno/tono
        values are coverage.py's synthetic code-object entry/exit markers
        (see coverage/sqldata.py `arcs()` docstring), not real source lines,
        and must be excluded rather than matched against `line`.
        """
        if line <= 0:
            return "line-absent", []
        cur.execute(
            "SELECT DISTINCT c.context FROM arc a "
            "JOIN context c ON c.id = a.context_id "
            "WHERE a.file_id = ? AND (a.fromno = ? OR a.tono = ?)",
            (file_id, line, line),
        )
        contexts = [ctx_str for (ctx_str,) in cur.fetchall()]
        tests = [_strip_context_suffix(c) for c in contexts if c]
        return _classify(tests, static=any(not c for c in contexts))

    def close(self) -> None:
        with self._lock:
            self._conn.close()
