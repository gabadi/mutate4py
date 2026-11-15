"""Step handlers for features/test-selection.feature (per-mutant test selection and directory run mode)."""

import os
import re
import subprocess
import sys
import tempfile
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from acceptance.steps.nested_pytest_helpers import nested_pytest_env
from acceptance.steps.step_lib import make_registry
from mutate4py._plugin_neutralisation import neutralising_args

STEP_HANDLERS, step, run_step = make_registry()

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _run_mutate4py(cwd: str, *args: str) -> subprocess.CompletedProcess:
    # --project REPO_ROOT pins resolution to this repo's own editable install
    # (mirrors parallel_workers_steps.py::when_run_mutate4py): bare "uv run
    # mutate4py" resolves against whatever project uv discovers from cwd, and
    # since cwd here is a scratch tempdir outside the repo, it falls through
    # to any globally `uv tool install`-ed mutate4py on PATH instead of the
    # local dev build under test.
    return subprocess.run(
        ["uv", "run", "--project", REPO_ROOT, "python", "-m", "mutate4py"] + list(args),
        capture_output=True,
        text=True,
        cwd=cwd,
        env=nested_pytest_env(),
    )


def _write_test(path: str, body: str) -> None:
    with open(path, "w") as f:
        f.write(body)


class Context:
    def __init__(self):
        self.tmpdir: str | None = None
        self.src_path: str | None = None
        self.log_path: str | None = None
        self.cli_result: subprocess.CompletedProcess | None = None
        self.dir_path: str | None = None
        self.dir_files: list[str] = []


ctx = Context()


def _reset_ctx():
    ctx.tmpdir = None
    ctx.src_path = None
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


def _calls_body(calls: tuple[str, ...]) -> str:
    """A test module whose test_dummy calls each named function on (2, 1), so the
    run's Measurement covers their sites under test_dummy's own context."""
    body = "from sample import " + ", ".join(calls) + "\n\n\ndef test_dummy():\n"
    body += "".join(f"    {name}(2, 1)\n" for name in calls)
    return body


def _write_uv_project_files(d: str) -> None:
    """A minimal uv project whose dev group declares pytest, so a real
    --max-workers run's per-Worker `uv sync` provisioning succeeds against
    this tmpdir and the Worker venv can run pytest. Mirrors
    parallel_workers_steps.py's _make_project_dir(), including no pre-made
    uv.lock (it would not list pytest). The dev group also names pytest-cov: the
    run's nested pytest loads it explicitly because autoload is off
    (nested_pytest_helpers.py), so the Worker venv must have it. Only the composition scenario's
    Worker copies need this; every other scenario here stays on the serial
    path and never shells out to uv."""
    with open(os.path.join(d, "pyproject.toml"), "w") as f:
        f.write(
            textwrap.dedent("""\
                [project]
                name = "test-project"
                version = "0.1.0"
                requires-python = ">=3.11"
                dependencies = []

                [dependency-groups]
                dev = ["pytest==9.1.1", "pytest-cov==7.1.0"]
            """)
        )


def _write_arg_logging_fixture(cwd: str, log_path: str, test_body: str) -> None:
    """A real pytest project whose conftest logs the exact args each pytest run
    received, one line per invocation (mirrors the old shell stand-in's
    `echo "ARGS:[$*]"`), next to the given test_dummy.py body.

    The hook fires even when a given node ID doesn't exist. It reads
    `config.invocation_params.args`, not `sys.argv`: the forking executor runs
    each mutant via an in-process `pytest.main(args)` call in a forked child,
    which never touches the parent (mutate4py CLI) process's `sys.argv` — only
    `invocation_params.args` reflects the actual per-call args pytest was
    invoked with, correctly under both the forking and subprocess executors."""
    conftest_body = (
        "def pytest_configure(config):\n"
        f"    with open({log_path!r}, 'a') as f:\n"
        "        f.write('ARGS:[' + ' '.join(config.invocation_params.args) + ']\\n')\n"
    )
    _write_test(os.path.join(cwd, "conftest.py"), conftest_body)
    _write_test(os.path.join(cwd, "test_dummy.py"), test_body)


def _confirmation_runs() -> int:
    """How many Survivor confirmation runs the report's Time line counts (0 when it has none)."""
    found = re.search(r"confirmation \S+ \((\d+) run", ctx.cli_result.stdout)
    return int(found.group(1)) if found else 0


def _logged_runs() -> list[str]:
    """Every logged invocation's argv in run order, with issue 06's neutralising_args() flags
    (e.g. `--no-cov`) filtered out: this feature's own presence is covered by
    test_plugin_neutralisation.py, and test-selection's assertions are about which
    test file/nodeids get appended, an orthogonal concern that would otherwise fail
    whenever pytest-cov happens to be installed in the environment running these
    acceptance steps."""
    if not os.path.isfile(ctx.log_path):
        return []
    with open(ctx.log_path) as f:
        lines = [line for line in f.read().splitlines() if line]
    runs = []
    for line in lines:
        prefix, _, rest = line.partition("[")
        tokens = [t for t in rest.rstrip("]").split(" ") if t and t not in neutralising_args()]
        runs.append(f"{prefix}[{' '.join(tokens)}]")
    return runs


def _split_runs() -> tuple[list[str], list[str]]:
    """The logged runs before the Survivor confirmation runs, and the confirmation
    runs themselves (the report's Time line says how many of the last ones there are)."""
    runs = _logged_runs()
    cut = len(runs) - _confirmation_runs()
    return runs[:cut], runs[cut:]


def _mutant_run() -> str:
    """The argv of the last Mutant run: the last logged run before any confirmation run."""
    before, _ = _split_runs()
    return before[-1] if before else ""


# ── Given steps ──────────────────────────────────────────────────────────────


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
    tests_dir = os.path.join(d, "tests")
    os.makedirs(tests_dir, exist_ok=True)
    _write_test(os.path.join(tests_dir, "test_qa.py"), "def test_qa():\n    pass\n")


@step(r"a Python source file with covered mutation sites")
def given_source_with_covered_sites(m, params):
    _reset_ctx()
    d = _ensure_tmpdir()
    ctx.src_path = os.path.join(d, "sample.py")
    with open(ctx.src_path, "w") as f:
        f.write(_default_source())
    ctx.log_path = os.path.join(d, "invocations.log")
    _write_arg_logging_fixture(d, ctx.log_path, _calls_body(("calc",)))


@step(r"a Python source file with mutation sites covered by known tests")
def given_source_two_sites(m, params):
    _reset_ctx()
    d = _ensure_tmpdir()
    _write_uv_project_files(d)
    ctx.src_path = os.path.join(d, "sample.py")
    with open(ctx.src_path, "w") as f:
        f.write(textwrap.dedent("""\
            def f1(a, b):
                return a > b


            def f2(a, b):
                return a > b
        """))
    ctx.log_path = os.path.join(d, "invocations.log")
    _write_arg_logging_fixture(d, ctx.log_path, _calls_body(("f1", "f2")))


@step(r"a Python source file whose only sites run at import time")
def given_import_time_source(m, params):
    _reset_ctx()
    d = _ensure_tmpdir()
    ctx.src_path = os.path.join(d, "sample.py")
    with open(ctx.src_path, "w") as f:
        # Two sites on one module-level line: the comparison and the constant 1.
        f.write("CHECK = 2 > 1\n")
    ctx.log_path = os.path.join(d, "invocations.log")
    # Importing sample at collection time runs the module-level comparison outside
    # any test, so the Measurement records its line under the empty context only.
    _write_arg_logging_fixture(
        d, ctx.log_path, "import sample\n\n\ndef test_dummy():\n    pass\n"
    )


@step(r"a Python source file that no test reaches")
def given_unreached_source(m, params):
    _reset_ctx()
    d = _ensure_tmpdir()
    ctx.src_path = os.path.join(d, "sample.py")
    with open(ctx.src_path, "w") as f:
        f.write(_default_source())
    ctx.log_path = os.path.join(d, "invocations.log")
    _write_arg_logging_fixture(d, ctx.log_path, "def test_dummy():\n    pass\n")


@step(r"a Python source file with no tests")
def given_source_no_tests(m, params):
    _reset_ctx()
    d = _ensure_tmpdir()
    ctx.src_path = os.path.join(d, "sample.py")
    with open(ctx.src_path, "w") as f:
        f.write(_default_source())


# ── When steps ───────────────────────────────────────────────────────────────


@step(r"mutate4py is run on the directory in scan mode")
def when_run_dir_scan(m, params):
    d = os.path.dirname(ctx.dir_path)
    ctx.cli_result = _run_mutate4py(d, ctx.dir_path, "--scan")


@step(r"mutate4py is run on the directory in run mode and one file fails to parse")
def when_run_dir_run(m, params):
    d = os.path.dirname(ctx.dir_path)
    ctx.cli_result = _run_mutate4py(d, ctx.dir_path, "--pytest-args", "tests")


@step(r"mutate4py is run without extra flags")
def when_run_plain(m, params):
    d = _ensure_tmpdir()
    ctx.cli_result = _run_mutate4py(d, ctx.src_path)


@step(r'mutate4py is run with "--max-workers 4"')
def when_run_with_workers(m, params):
    d = _ensure_tmpdir()
    ctx.cli_result = _run_mutate4py(d, ctx.src_path, "--max-workers", "4")


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


@step(r'the output contains "([^"]*)"')
def then_output_contains(m, params):
    # The no-tests error is logged on the single-file path's stdout, so search both streams.
    expected = params.get("text") or m.group(1)
    output = ctx.cli_result.stdout + ctx.cli_result.stderr
    assert expected in output, (
        f"Expected '{expected}' in output:\n"
        f"stdout:\n{ctx.cli_result.stdout}\nstderr:\n{ctx.cli_result.stderr}"
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


@step(r'the report line "([^"]*)" is printed')
def then_report_line(m, params):
    expected = params.get("line") or m.group(1)
    assert expected in ctx.cli_result.stdout, (
        f"Expected '{expected}' in stdout:\n{ctx.cli_result.stdout}"
    )


@step(r'the "Test selection:" line follows "Uncovered:" and precedes "Survivors:"')
def then_selection_line_order(m, params):
    lines = ctx.cli_result.stdout.splitlines()

    def index_of(prefix: str) -> int:
        for i, line in enumerate(lines):
            if line.startswith(prefix):
                return i
        raise AssertionError(f"No '{prefix}' line in:\n{ctx.cli_result.stdout}")

    uncovered = index_of("Uncovered:")
    selection = index_of("Test selection:")
    survivors = index_of("Survivors:")
    assert uncovered < selection < survivors, (
        f"Expected Uncovered < Test selection < Survivors in:\n{ctx.cli_result.stdout}"
    )


@step(r'that mutant\'s test command is "([^"]*)"')
def then_test_command_is(m, params):
    expected = params.get("cmd") or m.group(1)
    _, _, expected_args = expected.partition(" ")
    assert _mutant_run() == f"ARGS:[{expected_args}]", (
        f"Expected appended args '{expected_args}', got: {_mutant_run()!r}\n"
        f"stdout:\n{ctx.cli_result.stdout}"
    )


@step(r'that mutant\'s test command is the full "--pytest-args" verbatim')
def then_test_command_is_verbatim(m, params):
    assert _mutant_run() == "ARGS:[]", (
        f"Expected no appended args, got: {_mutant_run()!r}\nstdout:\n{ctx.cli_result.stdout}"
    )


@step(r'the survivor\'s confirmation run is the full "--pytest-args" verbatim')
def then_confirmation_is_verbatim(m, params):
    _, confirmations = _split_runs()
    count = _confirmation_runs()
    assert count >= 1, f"Expected a Survivor confirmation run in:\n{ctx.cli_result.stdout}"
    assert confirmations == ["ARGS:[]"] * count, (
        f"Expected verbatim confirmation args, got: {confirmations!r}\n"
        f"stdout:\n{ctx.cli_result.stdout}"
    )


@step(r"worker-N tokens are present in the progress lines")
def then_worker_tokens_present(m, params):
    assert "worker-" in ctx.cli_result.stdout, (
        f"Expected 'worker-' tokens in:\n{ctx.cli_result.stdout}"
    )
