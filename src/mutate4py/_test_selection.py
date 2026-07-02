"""Per-mutant test selection from a coverage.py SQLite context database."""

import sqlite3

__all__ = [
    "TestContextDB",
    "TestContextError",
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

    def _tests_for_line_bits(
        self, cur: sqlite3.Cursor, file_id: int, line: int
    ) -> list[str] | None:
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

    def _tests_for_line_arcs(
        self, cur: sqlite3.Cursor, file_id: int, line: int
    ) -> list[str] | None:
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
        tests = [
            _strip_context_suffix(ctx_str) for (ctx_str,) in cur.fetchall() if ctx_str
        ]
        return tests if tests else None

    def close(self) -> None:
        self._conn.close()


# mutate4py-manifest-begin
# {"version":1,"tested_at":"2026-07-02T02:09:38Z","module_hash":"ac70480b3109a4512d2784d8520d312f403a3680dcd1fd2d22f3a5aa2c9eccf2","functions":[{"id":"func/_numbits_to_lines","name":"_numbits_to_lines","line":17,"end_line":27,"hash":"912b98473a0e7a1305cf5a792a31275f64f058a25dbbc624651b15fa239a855b"},{"id":"func/_strip_context_suffix","name":"_strip_context_suffix","line":30,"end_line":34,"hash":"9cc4dfeab6b850139b00a28136df950b84c2f12383783d28478f69209deb5b0a"},{"id":"func/TestContextDB.__init__","name":"__init__","line":40,"end_line":48,"hash":"20d140b117522f76cf74f0388ac728a01a1f6dbbc1c073980c1817185950e66f"},{"id":"func/TestContextDB.tests_for_line","name":"tests_for_line","line":50,"end_line":63,"hash":"4874c0e20866e9a8f6496d7d2bc7f3e3c44dd62ab4bef8d781d5860b85ac5cbb"},{"id":"func/TestContextDB._tests_for_line_bits","name":"_tests_for_line_bits","line":65,"end_line":80,"hash":"691e7e59fdc9fb2ee063d2e9a85e883ce44a0b33c51d214cf858383cb20c3cca"},{"id":"func/TestContextDB._tests_for_line_arcs","name":"_tests_for_line_arcs","line":82,"end_line":105,"hash":"502784ca566d14670f3345a795285cb418c32e0b65d9f1b8a2f7fb60a9a01329"},{"id":"func/TestContextDB.close","name":"close","line":107,"end_line":108,"hash":"88de2b640cd4c3ceccd104505ba73e6f16f5991e9952fe69a08328537aa1b200"}]}
# mutate4py-manifest-end
