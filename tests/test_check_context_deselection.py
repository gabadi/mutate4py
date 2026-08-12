"""Tests for scripts/check_context_deselection.py.

Covers the gate described in issue #54: no test recorded as a named context
in `.coverage` may be deselected by the `mutate` recipe's --pytest-args, since
that silently turns a Mutant `killed` with nothing having tested it.
"""

import sqlite3
import subprocess

import pytest

from check_context_deselection import (
    GateError,
    Violation,
    check,
    collect_node_ids,
    files_for_context_ids,
    main,
    named_contexts,
)


def _make_coverage_db(db_path, arcs, *, has_arcs=True):
    """Create a minimal .coverage SQLite db.

    arcs: {source_path: {context_str: {(fromno, tono), ...}}}
    An empty context_str ("") represents the whole-run static context.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE meta (key TEXT, value TEXT);
        CREATE TABLE file (id INTEGER PRIMARY KEY, path TEXT);
        CREATE TABLE context (id INTEGER PRIMARY KEY, context TEXT);
        CREATE TABLE arc (file_id INTEGER, context_id INTEGER, fromno INTEGER, tono INTEGER);
    """)
    cur.execute("INSERT INTO meta(key, value) VALUES ('has_arcs', ?)", ("1" if has_arcs else "0",))
    cur.execute("INSERT INTO context(context) VALUES ('')")  # id=1, the empty/static context

    file_ids = {}
    context_ids = {"": 1}
    for path in arcs:
        cur.execute("INSERT INTO file(path) VALUES (?)", (path,))
        file_ids[path] = cur.lastrowid

    for path, ctx_map in arcs.items():
        for ctx_str, arc_set in ctx_map.items():
            if ctx_str not in context_ids:
                cur.execute("INSERT INTO context(context) VALUES (?)", (ctx_str,))
                context_ids[ctx_str] = cur.lastrowid
            for fromno, tono in arc_set:
                cur.execute(
                    "INSERT INTO arc(file_id, context_id, fromno, tono) VALUES (?, ?, ?, ?)",
                    (file_ids[path], context_ids[ctx_str], fromno, tono),
                )
    conn.commit()
    conn.close()
    return context_ids


# --- named_contexts ---------------------------------------------------------


@pytest.mark.unit
def test_named_contexts_strips_run_suffix_and_excludes_empty(tmp_path):
    db_path = tmp_path / ".coverage"
    _make_coverage_db(
        db_path,
        {
            "/repo/src/mutate4py/_a.py": {
                "tests/test_a.py::test_one|run": {(1, 2)},
                "tests/test_b.py::test_two|run": {(3, 4)},
            }
        },
    )

    result = named_contexts(db_path)

    assert set(result.keys()) == {"tests/test_a.py::test_one", "tests/test_b.py::test_two"}


@pytest.mark.unit
def test_named_contexts_missing_db_raises_gate_error(tmp_path):
    with pytest.raises(GateError, match="does not exist"):
        named_contexts(tmp_path / "nope.coverage")


# --- collect_node_ids --------------------------------------------------------


@pytest.mark.unit
def test_collect_node_ids_parses_unindented_double_colon_lines(monkeypatch, tmp_path):
    stdout = (
        "tests/test_a.py::test_one\n"
        "tests/test_a.py::test_two[param]\n"
        "  <Warning some indented note with :: in it>\n"
        "\n"
        "2/2 tests collected in 0.01s\n"
    )

    def fake_run(cmd, cwd, capture_output, text, check):
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = collect_node_ids(["-m", "not integration"], tmp_path)

    assert result == ["tests/test_a.py::test_one", "tests/test_a.py::test_two[param]"]


@pytest.mark.unit
def test_collect_node_ids_raises_on_pytest_failure(monkeypatch, tmp_path):
    def fake_run(cmd, cwd, capture_output, text, check):
        return subprocess.CompletedProcess(cmd, 4, stdout="", stderr="usage error")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(GateError, match="usage error"):
        collect_node_ids(["--bogus-flag"], tmp_path)


# --- files_for_context_ids ---------------------------------------------------


@pytest.mark.unit
def test_files_for_context_ids_joins_distinct_files(tmp_path):
    db_path = tmp_path / ".coverage"
    context_ids = _make_coverage_db(
        db_path,
        {
            "/repo/src/mutate4py/_a.py": {"tests/test_a.py::test_one|run": {(1, 2), (2, 3)}},
            "/repo/src/mutate4py/_b.py": {"tests/test_a.py::test_one|run": {(5, 6)}},
        },
    )

    result = files_for_context_ids(db_path, [context_ids["tests/test_a.py::test_one|run"]])

    assert result == ["/repo/src/mutate4py/_a.py", "/repo/src/mutate4py/_b.py"]


# --- check --------------------------------------------------------------------


@pytest.mark.unit
def test_check_reports_no_violations_when_every_named_context_is_selected(monkeypatch, tmp_path):
    db_path = tmp_path / ".coverage"
    _make_coverage_db(
        db_path,
        {"/repo/src/mutate4py/_a.py": {"tests/test_a.py::test_one|run": {(1, 2)}}},
    )
    monkeypatch.setattr(
        "check_context_deselection.collect_node_ids",
        lambda args, cwd: ["tests/test_a.py::test_one"],
    )

    violations = check(db_path, ["-m", "not integration"], tmp_path)

    assert violations == []


@pytest.mark.unit
def test_check_reports_violation_with_affected_files(monkeypatch, tmp_path):
    db_path = tmp_path / ".coverage"
    _make_coverage_db(
        db_path,
        {
            "/repo/src/mutate4py/_a.py": {"tests/test_a.py::test_one|run": {(1, 2)}},
            "/repo/src/mutate4py/_b.py": {"tests/test_hybrid.py::test_two|run": {(3, 4)}},
        },
    )
    # test_two carries @pytest.mark.integration and is deselected by `not integration`,
    # but still shows up as a named context (the Finding 1 bug).
    monkeypatch.setattr(
        "check_context_deselection.collect_node_ids",
        lambda args, cwd: ["tests/test_a.py::test_one"],
    )

    violations = check(db_path, ["-m", "not integration"], tmp_path)

    assert violations == [Violation("tests/test_hybrid.py::test_two", ["/repo/src/mutate4py/_b.py"])]


@pytest.mark.unit
def test_check_no_violation_when_an_integration_test_has_no_named_context(monkeypatch, tmp_path):
    """`integration` (ADR 0018) means invisible to --cov-context=test by
    definition, so an integration-marked test collected but never recorded
    as a named context is the correct, expected state -- not a partial
    `.coverage` build. `check` must not treat this as a GateError (there
    used to be a "no integration test overlaps a named context" sanity
    check here; it was removed for being backwards, see `check`'s
    docstring)."""
    db_path = tmp_path / ".coverage"
    _make_coverage_db(
        db_path,
        {"/repo/src/mutate4py/_a.py": {"tests/test_a.py::test_one|run": {(1, 2)}}},
    )
    monkeypatch.setattr(
        "check_context_deselection.collect_node_ids",
        lambda args, cwd: ["tests/test_a.py::test_one"],
    )

    violations = check(db_path, ["-m", "not integration"], tmp_path)

    assert violations == []


@pytest.mark.unit
def test_check_refuses_when_unit_half_missing(monkeypatch, tmp_path):
    db_path = tmp_path / ".coverage"
    _make_coverage_db(
        db_path,
        {"/repo/src/mutate4py/_a.py": {"tests/test_hybrid.py::test_two|run": {(1, 2)}}},
    )
    monkeypatch.setattr(
        "check_context_deselection.collect_node_ids",
        lambda args, cwd: ["tests/test_a.py::test_one"],  # collected, but never a named context
    )

    with pytest.raises(GateError, match="unit|not integration"):
        check(db_path, ["-m", "not integration"], tmp_path)


@pytest.mark.unit
def test_check_refuses_when_coverage_db_missing(tmp_path):
    with pytest.raises(GateError, match="does not exist"):
        check(tmp_path / "nope.coverage", ["-m", "not integration"], tmp_path)


# --- main (CLI) ---------------------------------------------------------------


@pytest.mark.unit
def test_main_exits_0_and_prints_ok_when_no_violations(monkeypatch, tmp_path, capsys):
    db_path = tmp_path / ".coverage"
    _make_coverage_db(
        db_path,
        {"/repo/src/mutate4py/_a.py": {"tests/test_a.py::test_one|run": {(1, 2)}}},
    )
    monkeypatch.setattr(
        "check_context_deselection.collect_node_ids",
        lambda args, cwd: ["tests/test_a.py::test_one"] if "not integration" in " ".join(args) else [],
    )

    exit_code = main(["--coverage-db", str(db_path), "--cwd", str(tmp_path)])

    assert exit_code == 0
    assert "no context-deselection violations" in capsys.readouterr().out


@pytest.mark.unit
def test_main_exits_1_and_names_offenders_when_violations_found(monkeypatch, tmp_path, capsys):
    db_path = tmp_path / ".coverage"
    _make_coverage_db(
        db_path,
        {"/repo/src/mutate4py/_b.py": {"tests/test_hybrid.py::test_two|run": {(3, 4)}}},
    )
    monkeypatch.setattr(
        "check_context_deselection.collect_node_ids",
        lambda args, cwd: [] if "not integration" in " ".join(args) else ["tests/test_hybrid.py::test_two"],
    )

    exit_code = main(["--coverage-db", str(db_path), "--cwd", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "tests/test_hybrid.py::test_two" in captured.err
    assert "_b.py" in captured.err


@pytest.mark.unit
def test_main_exits_1_with_clear_message_on_gate_error(tmp_path, capsys):
    exit_code = main(["--coverage-db", str(tmp_path / "nope.coverage"), "--cwd", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "does not exist" in captured.err
