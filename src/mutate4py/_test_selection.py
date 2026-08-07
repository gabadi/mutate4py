"""Per-mutant test selection from a coverage.py SQLite context database."""

import sqlite3

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


def _classify(tests: list[str], static: bool) -> tuple[str, list[str]]:
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
        try:
            self._conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        except sqlite3.OperationalError as e:
            raise TestContextError(f"cannot open coverage db: {e}") from e
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
        cur = self._conn.cursor()
        cur.execute("SELECT id FROM file WHERE path = ?", (source_path,))
        row = cur.fetchone()
        if row is None:
            return "file-absent", []
        file_id = row[0]
        if self._has_arcs:
            return self._tests_for_line_arcs(cur, file_id, line)
        return self._tests_for_line_bits(cur, file_id, line)

    def _tests_for_line_bits(
        self, cur: sqlite3.Cursor, file_id: int, line: int
    ) -> tuple[str, list[str]]:
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
        return _classify(tests, static)

    def _tests_for_line_arcs(
        self, cur: sqlite3.Cursor, file_id: int, line: int
    ) -> tuple[str, list[str]]:
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
        return _classify(tests, any(not c for c in contexts))

    def close(self) -> None:
        self._conn.close()


# mutate4py-manifest-begin
# {"version":1,"tested_at":"2026-08-07T00:48:58Z","module_hash":"d8c3822d21350b51f9e835eb428a68968bdddf88f8de7d503b63d53d62390404","functions":[{"id":"func/_numbits_to_lines","name":"_numbits_to_lines","line":18,"end_line":28,"hash":"912b98473a0e7a1305cf5a792a31275f64f058a25dbbc624651b15fa239a855b"},{"id":"func/_classify","name":"_classify","line":31,"end_line":37,"hash":"a6d0d868d5a63b848795252ceee0750494aa98c57f6c3b038f629a59a67de82e"},{"id":"func/_strip_context_suffix","name":"_strip_context_suffix","line":40,"end_line":44,"hash":"9cc4dfeab6b850139b00a28136df950b84c2f12383783d28478f69209deb5b0a"},{"id":"func/TestContextDB.__init__","name":"__init__","line":50,"end_line":58,"hash":"20d140b117522f76cf74f0388ac728a01a1f6dbbc1c073980c1817185950e66f"},{"id":"func/TestContextDB.tests_for_line","name":"tests_for_line","line":60,"end_line":79,"hash":"d67cceaf6cf3895492d205be59099e2f7c476e5e0ff55616882ec7d740965957"},{"id":"func/TestContextDB._tests_for_line_bits","name":"_tests_for_line_bits","line":81,"end_line":99,"hash":"e88eb762657473eb2bf8e66479bb07391290e9bcf915134924170e96e4e473ab"},{"id":"func/TestContextDB._tests_for_line_arcs","name":"_tests_for_line_arcs","line":101,"end_line":123,"hash":"f6b46ba82b5421476cca17aa4155fe2ef082680f1b3119783ebbaf806c1beac0"},{"id":"func/TestContextDB.close","name":"close","line":125,"end_line":126,"hash":"88de2b640cd4c3ceccd104505ba73e6f16f5991e9952fe69a08328537aa1b200"}]}
# mutate4py-manifest-end
