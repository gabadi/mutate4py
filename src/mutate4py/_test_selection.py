"""Per-mutant test selection from a coverage.py SQLite context database."""

import sqlite3
import threading

__all__ = [
    "TestContextDB",
    "TestContextError",
    "_classify",
    "_is_dynamic_context",
    "_numbits_to_lines",
    "_strip_context_suffix",
]

# pytest-cov's TestContextPlugin.switch_context() names every context it
# creates "<pytest node id>|setup" / "|run" / "|teardown" -- see
# pytest_cov/plugin.py. That is the *only* thing that produces this suffix:
# mutate4py's own isolated-session build (_test_context_build.py) drives
# coverage.py's static `--context=<node id>` directly, never through
# switch_context(), so its context strings never carry it. The suffix is
# therefore proof a context was recorded by a single shared dynamic-context
# collector session -- the method docs/adr/0021 proved silently drops every
# covering test but the first to reach a shared line or arc, for any db it
# built, not just unlucky lines within it.
_DYNAMIC_CONTEXT_PHASES = frozenset({"setup", "run", "teardown"})


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


def _is_dynamic_context(ctx_str: str) -> bool:
    """True if ctx_str carries pytest-cov's dynamic-context phase suffix.

    See _DYNAMIC_CONTEXT_PHASES above for why this suffix alone proves the
    context came from the single-shared-session method ADR 0021 rejected.
    """
    if "|" not in ctx_str:
        return False
    return ctx_str.rsplit("|", 1)[1] in _DYNAMIC_CONTEXT_PHASES


def _classify(tests: list[str], *, static: bool, dynamic: bool = False) -> tuple[str, list[str]]:
    """Fold a line's matched contexts into an outcome (see `tests_for_line`).

    dynamic means at least one of tests was named by a dynamic (pytest-cov
    switch_context) context: that build method can silently under-list
    covering tests (ADR 0021), so the result can never be trusted as
    "narrowed" -- it comes back "under-listed" instead, tests included so
    the caller can still see who mutate4py knows about even though it
    won't run only them.
    """
    if tests and dynamic:
        return "under-listed", tests
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


def _tally_contexts(ctx_strs: list[str]) -> tuple[list[str], bool, bool]:
    """Fold a line's matched context strings into (tests, static, dynamic).

    An empty ctx_str is coverage.py's marker for the whole-run (no-test)
    context, so it sets `static` rather than naming a test. Shared by both
    `_tests_for_line_bits` and `_tests_for_line_arcs`, which differ only in
    how they collect the matching rows.
    """
    tests: list[str] = []
    static = False
    dynamic = False
    for ctx_str in ctx_strs:
        if ctx_str:
            tests.append(_strip_context_suffix(ctx_str))
            dynamic = dynamic or _is_dynamic_context(ctx_str)
        else:
            static = True
    return tests, static, dynamic


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
          "narrowed"     — node_ids are the pytest node IDs covering the line,
                           all recorded by a static (isolated-session) context
          "under-listed" — node_ids covering the line include at least one
                           named by a dynamic (pytest-cov switch_context)
                           context; that method can silently drop covering
                           tests (ADR 0021), so this list can't be trusted
                           complete and must not be run as if it were
          "static"       — the line ran only under the empty (whole-run) context,
                           i.e. at import time, so no single test owns it
          "line-absent"  — the file is in the db but no context recorded the line
          "file-absent"  — the file is not in the db at all
        node_ids is empty for every outcome but "narrowed" and "under-listed".
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
        ctx_strs = [ctx_str for ctx_str, numbits in cur.fetchall() if line in _numbits_to_lines(numbits)]
        tests, static, dynamic = _tally_contexts(ctx_strs)
        return _classify(tests, static=static, dynamic=dynamic)

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
        tests, static, dynamic = _tally_contexts(contexts)
        return _classify(tests, static=static, dynamic=dynamic)

    def close(self) -> None:
        with self._lock:
            self._conn.close()
