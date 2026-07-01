"""Per-mutant test selection from a coverage.py SQLite context database."""

import sqlite3

__all__ = ["TestContextDB", "TestContextError", "_numbits_to_lines", "_strip_context_suffix"]


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


def _strip_context_suffix(context: str) -> str:
    """Strip the |<suffix> from a coverage.py context string to get the pytest node ID."""
    if "|" in context:
        return context.rsplit("|", 1)[0]
    return context


class TestContextDB:
    """Read-only view of a .coverage SQLite context database."""

    def __init__(self, db_path: str) -> None:
        try:
            self._conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        except sqlite3.OperationalError as e:
            raise TestContextError(f"cannot open coverage db: {e}") from e
        cur = self._conn.cursor()
        cur.execute("SELECT value FROM meta WHERE key = 'has_arcs'")
        row = cur.fetchone()
        self._has_arcs = bool(row and int(row[0]))

    def tests_for_line(self, source_path: str, line: int) -> list[str] | None:
        """Return pytest node IDs covering (source_path, line), or None if none do.

        None signals the caller to fall back to the full test command.
        """
        cur = self._conn.cursor()
        cur.execute("SELECT id FROM file WHERE path = ?", (source_path,))
        row = cur.fetchone()
        if row is None:
            return None
        file_id = row[0]
        if self._has_arcs:
            return self._tests_for_line_arcs(cur, file_id, line)
        return self._tests_for_line_bits(cur, file_id, line)

    def _tests_for_line_bits(self, cur: sqlite3.Cursor, file_id: int, line: int) -> list[str] | None:
        cur.execute(
            "SELECT c.context, lb.numbits FROM line_bits lb "
            "JOIN context c ON c.id = lb.context_id "
            "WHERE lb.file_id = ?",
            (file_id,),
        )
        tests: list[str] = []
        for ctx_str, numbits in cur.fetchall():
            if not ctx_str:
                continue
            if line in _numbits_to_lines(numbits):
                tests.append(_strip_context_suffix(ctx_str))
        return tests if tests else None

    def _tests_for_line_arcs(self, cur: sqlite3.Cursor, file_id: int, line: int) -> list[str] | None:
        """Branch-coverage mode: derive covering tests from the `arc` table.

        Mirrors coverage.py's own `SqliteDb.contexts_by_lineno`: a context
        "touches" a line if that line appears as either endpoint of an arc it
        recorded, provided the endpoint is positive. Negative fromno/tono
        values are coverage.py's synthetic code-object entry/exit markers
        (see coverage/sqldata.py `arcs()` docstring), not real source lines,
        and must be excluded rather than matched against `line`.
        """
        if line <= 0:
            return None
        cur.execute(
            "SELECT DISTINCT c.context FROM arc a "
            "JOIN context c ON c.id = a.context_id "
            "WHERE a.file_id = ? AND (a.fromno = ? OR a.tono = ?)",
            (file_id, line, line),
        )
        tests = [_strip_context_suffix(ctx_str) for (ctx_str,) in cur.fetchall() if ctx_str]
        return tests if tests else None

    def close(self) -> None:
        self._conn.close()
