"""Tests for _test_selection module (numbits decoding, context stripping, DB query)."""

import sqlite3
import threading

import pytest

from mutate4py._test_selection import (
    TestContextDB,
    TestContextError,
    _numbits_to_lines,
    _strip_context_suffix,
)


def _make_numbits(lines: set[int]) -> bytes:
    """Encode 1-based line numbers into coverage.py numbits format."""
    if not lines:
        return b""
    max_line = max(lines)
    n_bytes = (max_line + 7) // 8
    data = bytearray(n_bytes)
    for line in lines:
        byte_idx = (line - 1) // 8
        bit_idx = (line - 1) % 8
        data[byte_idx] |= 1 << bit_idx
    return bytes(data)


def _make_coverage_db(db_path: str, files: dict[str, dict[str, set[int]]]) -> None:
    """Create a minimal .coverage SQLite db (line-only coverage, has_arcs=0).

    files: {source_path: {context_str: set_of_lines}}
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE meta (key TEXT, value TEXT);
        CREATE TABLE file (id INTEGER PRIMARY KEY, path TEXT);
        CREATE TABLE context (id INTEGER PRIMARY KEY, context TEXT);
        CREATE TABLE line_bits (file_id INTEGER, context_id INTEGER, numbits BLOB);
        CREATE TABLE arc (file_id INTEGER, context_id INTEGER, fromno INTEGER, tono INTEGER);
    """)
    cur.execute("INSERT INTO meta(key, value) VALUES ('has_arcs', '0')")
    file_ids: dict[str, int] = {}
    for path in files:
        cur.execute("INSERT INTO file(path) VALUES (?)", (path,))
        file_ids[path] = cur.lastrowid  # type: ignore[assignment]

    context_ids: dict[str, int] = {}
    for ctx_map in files.values():
        for ctx_str in ctx_map:
            if ctx_str not in context_ids:
                cur.execute("INSERT INTO context(context) VALUES (?)", (ctx_str,))
                context_ids[ctx_str] = cur.lastrowid  # type: ignore[assignment]

    for path, ctx_map in files.items():
        for ctx_str, line_set in ctx_map.items():
            cur.execute(
                "INSERT INTO line_bits(file_id, context_id, numbits) VALUES (?, ?, ?)",
                (file_ids[path], context_ids[ctx_str], _make_numbits(line_set)),
            )

    conn.commit()
    conn.close()


def _make_coverage_db_arcs(db_path: str, files: dict[str, dict[str, list[tuple[int, int]]]]) -> None:
    """Create a minimal .coverage SQLite db in branch-coverage mode (has_arcs=1).

    files: {source_path: {context_str: list_of_(fromno, tono)_arcs}}

    Mirrors real coverage.py output under `[tool.coverage.run] branch = true`:
    execution data lives in `arc` (fromno/tono pairs), `line_bits` stays empty.
    Negative fromno/tono values are coverage.py's synthetic code-object
    entry/exit markers (see coverage/sqldata.py `arcs()` docstring) and must
    not be treated as real source lines.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE meta (key TEXT, value TEXT);
        CREATE TABLE file (id INTEGER PRIMARY KEY, path TEXT);
        CREATE TABLE context (id INTEGER PRIMARY KEY, context TEXT);
        CREATE TABLE line_bits (file_id INTEGER, context_id INTEGER, numbits BLOB);
        CREATE TABLE arc (file_id INTEGER, context_id INTEGER, fromno INTEGER, tono INTEGER);
    """)
    cur.execute("INSERT INTO meta(key, value) VALUES ('has_arcs', '1')")
    file_ids: dict[str, int] = {}
    for path in files:
        cur.execute("INSERT INTO file(path) VALUES (?)", (path,))
        file_ids[path] = cur.lastrowid  # type: ignore[assignment]

    context_ids: dict[str, int] = {}
    for ctx_map in files.values():
        for ctx_str in ctx_map:
            if ctx_str not in context_ids:
                cur.execute("INSERT INTO context(context) VALUES (?)", (ctx_str,))
                context_ids[ctx_str] = cur.lastrowid  # type: ignore[assignment]

    for path, ctx_map in files.items():
        for ctx_str, arcs in ctx_map.items():
            for fromno, tono in arcs:
                cur.execute(
                    "INSERT INTO arc(file_id, context_id, fromno, tono) VALUES (?, ?, ?, ?)",
                    (file_ids[path], context_ids[ctx_str], fromno, tono),
                )

    conn.commit()
    conn.close()


# ── numbits decoding ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_numbits_empty_bytes():
    assert _numbits_to_lines(b"") == set()


@pytest.mark.unit
def test_numbits_single_byte_first_bit():
    assert _numbits_to_lines(bytes([0b00000001])) == {1}


@pytest.mark.unit
def test_numbits_single_byte_last_bit():
    assert _numbits_to_lines(bytes([0b10000000])) == {8}


@pytest.mark.unit
def test_numbits_second_byte_first_bit():
    assert _numbits_to_lines(bytes([0, 0b00000001])) == {9}


@pytest.mark.unit
def test_numbits_multiple_lines_same_byte():
    assert _numbits_to_lines(bytes([0b00000101])) == {1, 3}


@pytest.mark.unit
def test_numbits_roundtrip(tmp_path):
    lines = {1, 5, 8, 9, 16}
    assert _numbits_to_lines(_make_numbits(lines)) == lines


# ── context stripping ──────────────────────────────────────────────────────────


@pytest.mark.unit
def test_strip_context_no_pipe():
    assert _strip_context_suffix("tests/foo.py::test_bar") == "tests/foo.py::test_bar"


@pytest.mark.unit
def test_strip_context_run_suffix():
    assert _strip_context_suffix("tests/foo.py::test_bar|run") == "tests/foo.py::test_bar"


@pytest.mark.unit
def test_strip_context_other_suffix():
    assert _strip_context_suffix("tests/foo.py::test_bar|something") == "tests/foo.py::test_bar"


# ── TestContextDB queries ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_tests_for_line_returns_matching_test(tmp_path):
    db = tmp_path / ".coverage"
    _make_coverage_db(
        str(db),
        {
            "/src/foo.py": {
                "tests/test_foo.py::test_bar|run": {10, 11, 12},
                "tests/test_foo.py::test_baz|run": {20, 21},
            }
        },
    )
    ctx_db = TestContextDB(str(db))
    assert ctx_db.tests_for_line("/src/foo.py", 10) == (
        "narrowed",
        ["tests/test_foo.py::test_bar"],
    )
    ctx_db.close()


@pytest.mark.unit
def test_tests_for_line_returns_multiple_tests(tmp_path):
    db = tmp_path / ".coverage"
    _make_coverage_db(
        str(db),
        {
            "/src/foo.py": {
                "tests/test_foo.py::test_bar|run": {10},
                "tests/test_foo.py::test_baz|run": {10},
            }
        },
    )
    ctx_db = TestContextDB(str(db))
    outcome, tests = ctx_db.tests_for_line("/src/foo.py", 10)
    assert outcome == "narrowed"
    assert sorted(tests) == sorted(["tests/test_foo.py::test_bar", "tests/test_foo.py::test_baz"])
    ctx_db.close()


@pytest.mark.unit
def test_tests_for_line_line_absent_when_no_context_recorded_the_line(tmp_path):
    db = tmp_path / ".coverage"
    _make_coverage_db(
        str(db),
        {"/src/foo.py": {"tests/test_foo.py::test_bar|run": {10}}},
    )
    ctx_db = TestContextDB(str(db))
    assert ctx_db.tests_for_line("/src/foo.py", 999) == ("line-absent", [])
    ctx_db.close()


@pytest.mark.unit
def test_tests_for_line_file_absent_when_file_not_in_db(tmp_path):
    db = tmp_path / ".coverage"
    _make_coverage_db(
        str(db),
        {"/src/foo.py": {"tests/test_foo.py::test_bar|run": {10}}},
    )
    ctx_db = TestContextDB(str(db))
    assert ctx_db.tests_for_line("/src/bar.py", 10) == ("file-absent", [])
    ctx_db.close()


@pytest.mark.unit
def test_empty_context_only_is_static(tmp_path):
    """A line seen only under the empty (whole-run) context is import-time code."""
    db = tmp_path / ".coverage"
    _make_coverage_db(
        str(db),
        {
            "/src/foo.py": {
                "": {10},
                "tests/test_foo.py::test_bar|run": {20},
            }
        },
    )
    ctx_db = TestContextDB(str(db))
    assert ctx_db.tests_for_line("/src/foo.py", 10) == ("static", [])
    ctx_db.close()


@pytest.mark.unit
def test_empty_context_does_not_suppress_a_covering_test(tmp_path):
    """A named test wins over the empty context when both recorded the line."""
    db = tmp_path / ".coverage"
    _make_coverage_db(
        str(db),
        {
            "/src/foo.py": {
                "": {10},
                "tests/test_foo.py::test_bar|run": {10},
            }
        },
    )
    ctx_db = TestContextDB(str(db))
    assert ctx_db.tests_for_line("/src/foo.py", 10) == (
        "narrowed",
        ["tests/test_foo.py::test_bar"],
    )
    ctx_db.close()


@pytest.mark.unit
def test_missing_db_raises_test_context_error(tmp_path):
    with pytest.raises(TestContextError):
        TestContextDB(str(tmp_path / "nonexistent.coverage"))


@pytest.mark.unit
def test_tests_for_line_is_safe_across_concurrent_threads(tmp_path):
    """Regression: parallel Worker dispatch shares one TestContextDB across
    worker threads (see _workers.py::WorkerRunSettings). sqlite3 connections
    default to check_same_thread=True, so this used to raise
    "SQLite objects created in a thread can only be used in that same
    thread." the moment a second thread called tests_for_line."""
    db = tmp_path / ".coverage"
    _make_coverage_db(
        str(db),
        {
            "/src/foo.py": {
                "tests/test_foo.py::test_bar|run": {10},
                "tests/test_foo.py::test_baz|run": {20},
            }
        },
    )
    ctx_db = TestContextDB(str(db))
    errors: list[BaseException] = []
    results: list[tuple[str, list[str]]] = []
    lock = threading.Lock()

    def worker(line: int) -> None:
        try:
            outcome = ctx_db.tests_for_line("/src/foo.py", line)
        except BaseException as e:  # noqa: BLE001 - captured for assertion, not swallowed
            with lock:
                errors.append(e)
        else:
            with lock:
                results.append(outcome)

    threads = [threading.Thread(target=worker, args=(line,)) for line in ([10, 20] * 10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert results.count(("narrowed", ["tests/test_foo.py::test_bar"])) == 10
    assert results.count(("narrowed", ["tests/test_foo.py::test_baz"])) == 10
    ctx_db.close()


# ── TestContextDB queries: branch-coverage mode (arc table, has_arcs=1) ─────────


@pytest.mark.unit
def test_tests_for_line_arc_mode_matches_fromno(tmp_path):
    db = tmp_path / ".coverage"
    _make_coverage_db_arcs(
        str(db),
        {
            "/src/foo.py": {
                "tests/test_foo.py::test_bar|run": [(-1, 10), (10, 11), (11, -1)],
            }
        },
    )
    ctx_db = TestContextDB(str(db))
    assert ctx_db.tests_for_line("/src/foo.py", 10) == (
        "narrowed",
        ["tests/test_foo.py::test_bar"],
    )
    ctx_db.close()


@pytest.mark.unit
def test_tests_for_line_arc_mode_matches_tono(tmp_path):
    db = tmp_path / ".coverage"
    _make_coverage_db_arcs(
        str(db),
        {
            "/src/foo.py": {
                "tests/test_foo.py::test_bar|run": [(-1, 10), (10, 11), (11, -1)],
            }
        },
    )
    ctx_db = TestContextDB(str(db))
    assert ctx_db.tests_for_line("/src/foo.py", 11) == (
        "narrowed",
        ["tests/test_foo.py::test_bar"],
    )
    ctx_db.close()


@pytest.mark.unit
def test_tests_for_line_arc_mode_returns_multiple_tests(tmp_path):
    db = tmp_path / ".coverage"
    _make_coverage_db_arcs(
        str(db),
        {
            "/src/foo.py": {
                "tests/test_foo.py::test_bar|run": [(-1, 10), (10, -1)],
                "tests/test_foo.py::test_baz|run": [(-1, 10), (10, -1)],
            }
        },
    )
    ctx_db = TestContextDB(str(db))
    outcome, tests = ctx_db.tests_for_line("/src/foo.py", 10)
    assert outcome == "narrowed"
    assert sorted(tests) == sorted(["tests/test_foo.py::test_bar", "tests/test_foo.py::test_baz"])
    ctx_db.close()


@pytest.mark.unit
def test_tests_for_line_arc_mode_line_absent_for_unrecorded_line(tmp_path):
    db = tmp_path / ".coverage"
    _make_coverage_db_arcs(
        str(db),
        {"/src/foo.py": {"tests/test_foo.py::test_bar|run": [(-1, 10), (10, -1)]}},
    )
    ctx_db = TestContextDB(str(db))
    assert ctx_db.tests_for_line("/src/foo.py", 999) == ("line-absent", [])
    ctx_db.close()


@pytest.mark.unit
def test_tests_for_line_arc_mode_excludes_synthetic_entry_exit_sentinels(tmp_path):
    """Negative fromno/tono are code-object entry/exit markers, not real lines.

    A query for line -1 (or any negative/zero "line") must never match, even
    though -1 literally appears in the arc table as a synthetic marker.
    """
    db = tmp_path / ".coverage"
    _make_coverage_db_arcs(
        str(db),
        {"/src/foo.py": {"tests/test_foo.py::test_bar|run": [(-1, 10), (10, -1)]}},
    )
    ctx_db = TestContextDB(str(db))
    assert ctx_db.tests_for_line("/src/foo.py", -1) == ("line-absent", [])
    assert ctx_db.tests_for_line("/src/foo.py", 0) == ("line-absent", [])
    ctx_db.close()


@pytest.mark.unit
def test_tests_for_line_arc_mode_rejects_line_zero_even_when_an_arc_carries_it(
    tmp_path,
):
    """0 is not a 1-based line number, so it must not match however the db reads."""
    db = tmp_path / ".coverage"
    _make_coverage_db_arcs(
        str(db),
        {"/src/foo.py": {"tests/test_foo.py::test_bar|run": [(0, 10), (10, 0)]}},
    )
    ctx_db = TestContextDB(str(db))
    assert ctx_db.tests_for_line("/src/foo.py", 0) == ("line-absent", [])
    ctx_db.close()


@pytest.mark.unit
def test_tests_for_line_arc_mode_matches_line_one(tmp_path):
    """Line 1 is a real line, on the far side of the <= 0 guard's boundary."""
    db = tmp_path / ".coverage"
    _make_coverage_db_arcs(
        str(db),
        {"/src/foo.py": {"tests/test_foo.py::test_bar|run": [(-1, 1), (1, -1)]}},
    )
    ctx_db = TestContextDB(str(db))
    assert ctx_db.tests_for_line("/src/foo.py", 1) == (
        "narrowed",
        ["tests/test_foo.py::test_bar"],
    )
    ctx_db.close()


@pytest.mark.unit
def test_tests_for_line_arc_mode_empty_context_only_is_static(tmp_path):
    """A line seen only under the empty (whole-run) context is import-time code."""
    db = tmp_path / ".coverage"
    _make_coverage_db_arcs(
        str(db),
        {
            "/src/foo.py": {
                "": [(-1, 10), (10, -1)],
                "tests/test_foo.py::test_bar|run": [(-1, 20), (20, -1)],
            }
        },
    )
    ctx_db = TestContextDB(str(db))
    assert ctx_db.tests_for_line("/src/foo.py", 10) == ("static", [])
    ctx_db.close()


@pytest.mark.unit
def test_tests_for_line_arc_mode_empty_context_does_not_suppress_a_test(tmp_path):
    """A named test wins over the empty context when both recorded the line."""
    db = tmp_path / ".coverage"
    _make_coverage_db_arcs(
        str(db),
        {
            "/src/foo.py": {
                "": [(-1, 10), (10, -1)],
                "tests/test_foo.py::test_bar|run": [(-1, 10), (10, -1)],
            }
        },
    )
    ctx_db = TestContextDB(str(db))
    assert ctx_db.tests_for_line("/src/foo.py", 10) == (
        "narrowed",
        ["tests/test_foo.py::test_bar"],
    )
    ctx_db.close()


@pytest.mark.unit
def test_tests_for_line_arc_mode_file_absent_when_file_not_in_db(tmp_path):
    db = tmp_path / ".coverage"
    _make_coverage_db_arcs(
        str(db),
        {"/src/foo.py": {"tests/test_foo.py::test_bar|run": [(-1, 10), (10, -1)]}},
    )
    ctx_db = TestContextDB(str(db))
    assert ctx_db.tests_for_line("/src/bar.py", 10) == ("file-absent", [])
    ctx_db.close()
