"""Step handlers for features/test-selection.feature (per-mutant test selection)."""

import os
import sqlite3
import subprocess
import sys
import tempfile
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from acceptance.steps.step_lib import make_registry

STEP_HANDLERS, step, run_step = make_registry()


def _run_mutate4py(cwd: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "mutate4py"] + list(args),
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def _make_lcov(entries: dict[str, list[int]]) -> str:
    blocks = []
    for source_abs, lines in entries.items():
        da = "\n".join(f"DA:{ln},1" for ln in sorted(lines))
        blocks.append(f"SF:{source_abs}\n{da}\nend_of_record\n")
    return "".join(blocks)


def _write_test(path: str, body: str) -> None:
    with open(path, "w") as f:
        f.write(body)


def _write_context_db(db_path: str, files: dict[str, dict[str, set[int]]]) -> None:
    """Create a minimal .coverage SQLite context db (line_bits mode, has_arcs=0).

    files: {source_path: {context_str: set_of_covered_lines}}
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE meta (key TEXT, value TEXT);
        CREATE TABLE file (id INTEGER PRIMARY KEY, path TEXT);
        CREATE TABLE context (id INTEGER PRIMARY KEY, context TEXT);
        CREATE TABLE line_bits (file_id INTEGER, context_id INTEGER, numbits BLOB);
    """)
    cur.execute("INSERT INTO meta(key, value) VALUES ('has_arcs', '0')")
    for path, ctx_map in files.items():
        cur.execute("INSERT INTO file(path) VALUES (?)", (path,))
        file_id = cur.lastrowid
        for ctx_str, line_set in ctx_map.items():
            cur.execute("INSERT INTO context(context) VALUES (?)", (ctx_str,))
            context_id = cur.lastrowid
            cur.execute(
                "INSERT INTO line_bits(file_id, context_id, numbits) VALUES (?, ?, ?)",
                (file_id, context_id, _numbits(line_set)),
            )
    conn.commit()
    conn.close()


def _numbits(lines: set[int]) -> bytes:
    if not lines:
        return b""
    n_bytes = (max(lines) + 7) // 8
    data = bytearray(n_bytes)
    for line in lines:
        data[(line - 1) // 8] |= 1 << ((line - 1) % 8)
    return bytes(data)


class Context:
    def __init__(self):
        self.tmpdir: str | None = None
        self.src_path: str | None = None
        self.lcov_path: str | None = None
        self.db_path: str | None = None
        self.log_path: str | None = None
        self.cli_result: subprocess.CompletedProcess | None = None
        self.dir_path: str | None = None
        self.dir_files: list[str] = []


ctx = Context()


def _reset_ctx():
    ctx.tmpdir = None
    ctx.src_path = None
    ctx.lcov_path = None
    ctx.db_path = None
    ctx.log_path = None
    ctx.cli_result = None
    ctx.dir_path = None
    ctx.dir_files = []


def _ensure_tmpdir() -> str:
    if ctx.tmpdir is None:
        ctx.tmpdir = tempfile.mkdtemp()
    return ctx.tmpdir


def _default_source() -> str:
    """A source file with exactly one Compare site on line 2."""
    return "def calc(a, b):\n    return a > b\n"


def _write_arg_logging_fixture(cwd: str, log_path: str) -> None:
    """A real pytest project that always passes when invoked with no extra
    args, and logs the exact args pytest received (mirrors the old shell
    stand-in's `echo "ARGS:[$*]"`) via a pytest_configure hook — this fires
    even when a given node ID doesn't exist, since --pytest-args can no
    longer swap out the runner itself the way --test-command once did."""
    conftest_body = (
        "def pytest_configure(config):\n"
        "    import sys\n"
        f"    with open({log_path!r}, 'a') as f:\n"
        "        f.write('ARGS:[' + ' '.join(sys.argv[1:]) + ']\\n')\n"
    )
    _write_test(os.path.join(cwd, "conftest.py"), conftest_body)
    _write_test(os.path.join(cwd, "test_dummy.py"), "def test_dummy():\n    pass\n")


def _logged_args() -> str:
    """The last logged invocation's argv — the mutant run, not the baseline pass."""
    if not os.path.isfile(ctx.log_path):
        return ""
    with open(ctx.log_path) as f:
        lines = [line for line in f.read().splitlines() if line]
    return lines[-1] if lines else ""


# ── Given steps ──────────────────────────────────────────────────────────────


@step(r'a Python source file "([^"]*)" containing "([^"]*)"')
def given_named_source(m, params):
    _reset_ctx()
    d = _ensure_tmpdir()
    filename = params.get("filename") or m.group(1)
    content = params.get("content") or m.group(2)
    ctx.src_path = os.path.join(d, filename)
    with open(ctx.src_path, "w") as f:
        f.write(content + "\n")


@step(r'a directory "([^"]*)" containing two Python files "([^"]*)" and "([^"]*)"')
def given_dir_two_files(m, params):
    _reset_ctx()
    d = _ensure_tmpdir()
    ctx.dir_path = os.path.join(d, "src")
    os.makedirs(ctx.dir_path, exist_ok=True)
    ctx.dir_files = []
    for name in (m.group(2), m.group(3)):
        path = os.path.join(ctx.dir_path, name)
        with open(path, "w") as f:
            f.write("def f(a, b):\n    return a > b\n")
        ctx.dir_files.append(path)


@step(r'a directory "([^"]*)" containing Python files')
def given_dir_files(m, params):
    _reset_ctx()
    d = _ensure_tmpdir()
    ctx.dir_path = os.path.join(d, "src")
    os.makedirs(ctx.dir_path, exist_ok=True)
    good = os.path.join(ctx.dir_path, "a.py")
    with open(good, "w") as f:
        f.write("x = 1\n")
    # Sorts after a.py; the batch keeps going past its parse failure (see
    # _run_files_and_exit) but the aggregate exit code still reflects it.
    broken = os.path.join(ctx.dir_path, "b.py")
    with open(broken, "w") as f:
        f.write("def broken(:\n    pass\n")
    ctx.lcov_path = os.path.join(d, "cov.lcov")
    with open(ctx.lcov_path, "w") as f:
        f.write(_make_lcov({good: []}))
    tests_dir = os.path.join(d, "tests")
    os.makedirs(tests_dir, exist_ok=True)
    _write_test(os.path.join(tests_dir, "test_qa.py"), "def test_qa():\n    pass\n")


@step(r"a \.coverage db naming \"([^\"]*)\" as covering the mutated line")
def given_db_naming_test(m, params):
    _reset_ctx()
    d = _ensure_tmpdir()
    node_id = params.get("nodeId") or m.group(1)
    ctx.src_path = os.path.join(d, "sample.py")
    with open(ctx.src_path, "w") as f:
        f.write(_default_source())
    ctx.lcov_path = os.path.join(d, "cov.lcov")
    with open(ctx.lcov_path, "w") as f:
        f.write(_make_lcov({ctx.src_path: [2]}))
    ctx.db_path = os.path.join(d, ".coverage")
    _write_context_db(ctx.db_path, {ctx.src_path: {node_id: {2}}})
    ctx.log_path = os.path.join(d, "invocations.log")
    _write_arg_logging_fixture(d, ctx.log_path)


@step(r"a \.coverage db showing the mutated line only under the empty context")
def given_db_static_line(m, params):
    _reset_ctx()
    d = _ensure_tmpdir()
    ctx.src_path = os.path.join(d, "sample.py")
    with open(ctx.src_path, "w") as f:
        f.write(_default_source())
    ctx.lcov_path = os.path.join(d, "cov.lcov")
    with open(ctx.lcov_path, "w") as f:
        f.write(_make_lcov({ctx.src_path: [2]}))
    ctx.db_path = os.path.join(d, ".coverage")
    _write_context_db(ctx.db_path, {ctx.src_path: {"": {2}}})
    ctx.log_path = os.path.join(d, "invocations.log")
    _write_arg_logging_fixture(d, ctx.log_path)


@step(r'a \.coverage db in which the mutated line "([^"]*)"')
def given_db_disagreement(m, params):
    _reset_ctx()
    d = _ensure_tmpdir()
    state = params.get("state") or m.group(1)
    ctx.src_path = os.path.join(d, "sample.py")
    with open(ctx.src_path, "w") as f:
        f.write(_default_source())
    ctx.lcov_path = os.path.join(d, "cov.lcov")
    with open(ctx.lcov_path, "w") as f:
        f.write(_make_lcov({ctx.src_path: [2]}))
    ctx.db_path = os.path.join(d, ".coverage")
    if state == "is absent though LCOV-covered":
        # File is in the db, but no context recorded line 2 (only line 99).
        _write_context_db(ctx.db_path, {ctx.src_path: {"tests/test_x.py::test_a": {99}}})
    else:
        # File is entirely absent from the db.
        other = os.path.join(d, "other.py")
        _write_context_db(ctx.db_path, {other: {"tests/test_x.py::test_a": {1}}})
    ctx.log_path = os.path.join(d, "invocations.log")
    _write_arg_logging_fixture(d, ctx.log_path)


@step(r"a Python source file with covered mutation sites")
def given_source_with_covered_sites(m, params):
    _reset_ctx()
    d = _ensure_tmpdir()
    ctx.src_path = os.path.join(d, "sample.py")
    with open(ctx.src_path, "w") as f:
        f.write(_default_source())
    ctx.lcov_path = os.path.join(d, "cov.lcov")
    with open(ctx.lcov_path, "w") as f:
        f.write(_make_lcov({ctx.src_path: [2]}))
    ctx.log_path = os.path.join(d, "invocations.log")
    _write_arg_logging_fixture(d, ctx.log_path)


@step(r"a Python source file with mutation sites covered by known tests")
def given_source_two_sites(m, params):
    _reset_ctx()
    d = _ensure_tmpdir()
    ctx.src_path = os.path.join(d, "sample.py")
    with open(ctx.src_path, "w") as f:
        f.write(textwrap.dedent("""\
            def f1(a, b):
                return a > b


            def f2(a, b):
                return a > b
        """))
    ctx.lcov_path = os.path.join(d, "cov.lcov")
    with open(ctx.lcov_path, "w") as f:
        f.write(_make_lcov({ctx.src_path: [2, 6]}))
    ctx.log_path = os.path.join(d, "invocations.log")
    _write_arg_logging_fixture(d, ctx.log_path)


@step(r"a \.coverage db with per-test context data")
def given_db_per_test_context(m, params):
    d = _ensure_tmpdir()
    ctx.db_path = os.path.join(d, ".coverage")
    # Both sites execute only at import time here — narrowed vs. static is
    # irrelevant to this scenario, which only checks that --max-workers is
    # forced to serial when --test-contexts is supplied.
    _write_context_db(ctx.db_path, {ctx.src_path: {"": {2, 6}}})


# ── When steps ───────────────────────────────────────────────────────────────


@step(r'mutate4py is run with "--test-contexts /nonexistent/.coverage"')
def when_run_missing_contexts_file(m, params):
    d = _ensure_tmpdir()
    ctx.cli_result = _run_mutate4py(
        d, ctx.src_path, "--test-contexts", "/nonexistent/.coverage"
    )


@step(r"mutate4py is run on the directory in scan mode")
def when_run_dir_scan(m, params):
    d = os.path.dirname(ctx.dir_path)
    ctx.cli_result = _run_mutate4py(d, ctx.dir_path, "--scan")


@step(r"mutate4py is run on the directory in run mode and one file fails to parse")
def when_run_dir_run(m, params):
    d = os.path.dirname(ctx.dir_path)
    ctx.cli_result = _run_mutate4py(
        d, ctx.dir_path, "--lcov", ctx.lcov_path, "--pytest-args", "tests"
    )


@step(r'mutate4py is run with "--test-contexts \.coverage"')
def when_run_with_contexts(m, params):
    d = _ensure_tmpdir()
    ctx.cli_result = _run_mutate4py(
        d,
        ctx.src_path,
        "--lcov",
        ctx.lcov_path,
        "--pytest-args",
        "",
        "--test-contexts",
        ctx.db_path,
    )


@step(r'mutate4py is run without "--test-contexts"')
def when_run_without_contexts(m, params):
    d = _ensure_tmpdir()
    ctx.cli_result = _run_mutate4py(
        d, ctx.src_path, "--lcov", ctx.lcov_path, "--pytest-args", ""
    )


@step(r'mutate4py is run with "--test-contexts \.coverage --max-workers 4"')
def when_run_with_contexts_and_workers(m, params):
    d = _ensure_tmpdir()
    ctx.cli_result = _run_mutate4py(
        d,
        ctx.src_path,
        "--lcov",
        ctx.lcov_path,
        "--pytest-args",
        "",
        "--test-contexts",
        ctx.db_path,
        "--max-workers",
        "4",
    )


# ── Then steps ───────────────────────────────────────────────────────────────


@step(r"the exit code is (\d+)")
def then_exit_code(m, params):
    expected = int(params.get("code") or m.group(1))
    assert ctx.cli_result.returncode == expected, (
        f"Expected exit {expected}, got {ctx.cli_result.returncode}\n"
        f"stdout:\n{ctx.cli_result.stdout}\nstderr:\n{ctx.cli_result.stderr}"
    )


@step(r"the exit code is non-zero")
def then_exit_nonzero(m, params):
    assert ctx.cli_result.returncode != 0, (
        f"Expected non-zero exit, got 0\nstdout:\n{ctx.cli_result.stdout}"
    )


@step(r'stderr contains "([^"]*)"')
def then_stderr_contains(m, params):
    expected = params.get("hint") or m.group(1)
    assert expected in ctx.cli_result.stderr, (
        f"Expected '{expected}' in stderr:\n{ctx.cli_result.stderr}"
    )


@step(r'the output contains two "Mutation scan:" lines')
def then_two_scan_lines(m, params):
    stdout = ctx.cli_result.stdout
    count = stdout.count("Mutation scan:")
    assert count == 2, f"Expected 2 'Mutation scan:' lines, got {count}:\n{stdout}"
    assert len(ctx.dir_files) == 2
    for path in ctx.dir_files:
        assert f"Mutation scan: {path}" in stdout, (
            f"Expected a 'Mutation scan:' line naming {path}:\n{stdout}"
        )


@step(r'that mutant\'s test command is "([^"]*)"')
def then_test_command_is(m, params):
    expected = params.get("cmd") or m.group(1)
    _, _, expected_args = expected.partition(" ")
    assert _logged_args() == f"ARGS:[{expected_args}]", (
        f"Expected appended args '{expected_args}', got: {_logged_args()!r}\n"
        f"stdout:\n{ctx.cli_result.stdout}"
    )


@step(r'that mutant\'s test command is the full "--pytest-args" verbatim')
def then_test_command_is_verbatim(m, params):
    assert _logged_args() == "ARGS:[]", (
        f"Expected no appended args, got: {_logged_args()!r}\nstdout:\n{ctx.cli_result.stdout}"
    )


@step(r'the report line "([^"]*)" is printed')
def then_report_line(m, params):
    expected = params.get("line") or m.group(1)
    assert expected in ctx.cli_result.stdout, (
        f"Expected '{expected}' in stdout:\n{ctx.cli_result.stdout}"
    )


@step(r'no "Mutation Report" is printed')
def then_no_report(m, params):
    assert "Mutation Report" not in ctx.cli_result.stdout, (
        f"Unexpected 'Mutation Report' in stdout:\n{ctx.cli_result.stdout}"
    )


@step(r"after the run the source has no mutant spliced in")
def then_source_restored(m, params):
    with open(ctx.src_path) as f:
        content = f.read()
    assert ">=" not in content, f"Mutant still in source:\n{content}"


@step(r'no "Test selection:" line is printed')
def then_no_test_selection_line(m, params):
    assert "Test selection:" not in ctx.cli_result.stdout, (
        f"Unexpected 'Test selection:' line in:\n{ctx.cli_result.stdout}"
    )


@step(r"the run proceeds serially \(no worker-N tokens in output\)")
def then_serial_no_worker_tokens(m, params):
    assert "worker-" not in ctx.cli_result.stdout, (
        f"Unexpected 'worker-' token in:\n{ctx.cli_result.stdout}"
    )
