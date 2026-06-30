"""Tests for _test_selection module (numbits decoding, context stripping, DB query)."""

import sqlite3

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
    """Create a minimal .coverage SQLite db.

    files: {source_path: {context_str: set_of_lines}}
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE file (id INTEGER PRIMARY KEY, path TEXT);
        CREATE TABLE context (id INTEGER PRIMARY KEY, context TEXT);
        CREATE TABLE line_bits (file_id INTEGER, context_id INTEGER, numbits BLOB);
    """)
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


# ── numbits decoding ───────────────────────────────────────────────────────────


def test_numbits_empty_bytes():
    assert _numbits_to_lines(b"") == set()


def test_numbits_single_byte_first_bit():
    assert _numbits_to_lines(bytes([0b00000001])) == {1}


def test_numbits_single_byte_last_bit():
    assert _numbits_to_lines(bytes([0b10000000])) == {8}


def test_numbits_second_byte_first_bit():
    assert _numbits_to_lines(bytes([0, 0b00000001])) == {9}


def test_numbits_multiple_lines_same_byte():
    assert _numbits_to_lines(bytes([0b00000101])) == {1, 3}


def test_numbits_roundtrip(tmp_path):
    lines = {1, 5, 8, 9, 16}
    assert _numbits_to_lines(_make_numbits(lines)) == lines


# ── context stripping ──────────────────────────────────────────────────────────


def test_strip_context_no_pipe():
    assert _strip_context_suffix("tests/foo.py::test_bar") == "tests/foo.py::test_bar"


def test_strip_context_run_suffix():
    assert _strip_context_suffix("tests/foo.py::test_bar|run") == "tests/foo.py::test_bar"


def test_strip_context_other_suffix():
    assert _strip_context_suffix("tests/foo.py::test_bar|something") == "tests/foo.py::test_bar"


# ── TestContextDB queries ──────────────────────────────────────────────────────


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
    tests = ctx_db.tests_for_line("/src/foo.py", 10)
    assert tests == ["tests/test_foo.py::test_bar"]
    ctx_db.close()


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
    tests = ctx_db.tests_for_line("/src/foo.py", 10)
    assert sorted(tests) == sorted(
        ["tests/test_foo.py::test_bar", "tests/test_foo.py::test_baz"]
    )
    ctx_db.close()


def test_tests_for_line_returns_none_for_uncovered_line(tmp_path):
    db = tmp_path / ".coverage"
    _make_coverage_db(
        str(db),
        {"/src/foo.py": {"tests/test_foo.py::test_bar|run": {10}}},
    )
    ctx_db = TestContextDB(str(db))
    assert ctx_db.tests_for_line("/src/foo.py", 999) is None
    ctx_db.close()


def test_tests_for_line_returns_none_when_file_not_in_db(tmp_path):
    db = tmp_path / ".coverage"
    _make_coverage_db(
        str(db),
        {"/src/foo.py": {"tests/test_foo.py::test_bar|run": {10}}},
    )
    ctx_db = TestContextDB(str(db))
    assert ctx_db.tests_for_line("/src/bar.py", 10) is None
    ctx_db.close()


def test_empty_context_string_skipped(tmp_path):
    """Empty context (overall run, not per-test) must not appear in results."""
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
    assert ctx_db.tests_for_line("/src/foo.py", 10) is None
    ctx_db.close()


def test_missing_db_raises_test_context_error(tmp_path):
    with pytest.raises(TestContextError):
        TestContextDB(str(tmp_path / "nonexistent.coverage"))
