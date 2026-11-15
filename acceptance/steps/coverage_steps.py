"""Step handlers for features/coverage.feature (F3: Measurement as coverage, the core refusal, removed flags)."""

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from acceptance.steps.coverage_helpers import (
    HALF_TAKEN_BRANCH_SOURCE,
    HALF_TAKEN_BRANCH_TEST,
    IMPORT_TIME_SOURCE,
    IMPORTING_CONFTEST,
    PASSING_TEST,
    assert_exit_status,
    assert_no_backup_beside,
    assert_no_partition_counts,
    assert_output_contains,
    assert_stdout_contains,
    called_names,
    core_recording_test,
    first_recorded_core,
    removed_flag_refusal,
    removed_flag_tokens,
    step_param,
)
from acceptance.steps.run_loop_helpers import (
    ROOT_CONFTEST,
    SAMPLE_MODULE,
    compare_source,
    reaching_test_body,
)
from acceptance.steps.nested_pytest_helpers import nested_pytest_env
from acceptance.steps.step_lib import make_registry

STEP_HANDLERS, step, run_step = make_registry()


class Context:
    def __init__(self):
        self.tmpdir: str | None = None
        self.source_path: str | None = None
        self.source_bytes: bytes | None = None
        self.cli_result: subprocess.CompletedProcess | None = None
        self.core_record: str | None = None
        self.env: dict[str, str] = {}

    def reset(self) -> str:
        self.tmpdir = tempfile.mkdtemp()
        self.source_path = os.path.join(self.tmpdir, f"{SAMPLE_MODULE}.py")
        self.source_bytes = None
        self.cli_result = None
        self.core_record = None
        self.env = {}
        return self.tmpdir

    def root(self) -> str:
        assert self.tmpdir is not None, "no project written"
        return self.tmpdir

    def write(self, relative: str, text: str) -> None:
        path = os.path.join(self.root(), relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
        if relative == f"{SAMPLE_MODULE}.py":
            self.source_bytes = text.encode()

    def run(self, *args: str) -> None:
        env = nested_pytest_env({**os.environ, **self.env})
        self.cli_result = subprocess.run(
            ["uv", "run", "mutate4py", *args],
            capture_output=True,
            text=True,
            cwd=self.root(),
            env=env,
        )


ctx = Context()


# ── Background ────────────────────────────────────────────────────────────────


@step(r"a pytest project whose module has three comparison sites in functions f1, f2 and f3")
def given_three_site_project(m, params):
    ctx.reset()
    source, _ = compare_source(3)
    ctx.write(f"{SAMPLE_MODULE}.py", source)
    # An empty conftest.py puts the project root on sys.path for the tests.
    ctx.write("conftest.py", ROOT_CONFTEST)
    ctx.write("tests/test_qa.py", PASSING_TEST)


# ── Given steps ───────────────────────────────────────────────────────────────


@step(r'the tests call "([^"]*)"')
def given_tests_call(m, params):
    names = called_names(step_param(m, params, "called"))
    ctx.write("tests/test_qa.py", reaching_test_body(SAMPLE_MODULE, names) if names else PASSING_TEST)


@step(r"a module whose only site is a module-level line that no test calls")
def given_import_time_module(m, params):
    ctx.write(f"{SAMPLE_MODULE}.py", IMPORT_TIME_SOURCE)
    ctx.write("tests/test_qa.py", PASSING_TEST)


@step(r"a conftest that imports the module while pytest loads it")
def given_importing_conftest(m, params):
    ctx.write("conftest.py", IMPORTING_CONFTEST)


@step(r"a function whose comparison sits in a branch that the tests take only one way")
def given_half_taken_branch(m, params):
    ctx.write(f"{SAMPLE_MODULE}.py", HALF_TAKEN_BRANCH_SOURCE)
    ctx.write("tests/test_qa.py", HALF_TAKEN_BRANCH_TEST)


@step(r"a test that records the coverage core it ran under")
def given_core_recording_test(m, params):
    ctx.core_record = os.path.join(ctx.root(), "cores.txt")
    ctx.write("tests/test_qa.py", core_recording_test(ctx.core_record))


@step(r'the caller\'s environment asks for the "([^"]*)" core')
def given_caller_core(m, params):
    ctx.env["COVERAGE_CORE"] = step_param(m, params, "core")


# ── When steps ────────────────────────────────────────────────────────────────


@step(r"I run mutate4py on that source with its tests")
def when_run_with_tests(m, params):
    ctx.run(ctx.source_path, "--pytest-args", "tests", "--allow-survivors")


@step(r'I run mutate4py on that source with the removed flag "([^"]*)"')
def when_run_with_removed_flag(m, params):
    flag = step_param(m, params, "flag")
    ctx.run(ctx.source_path, "--pytest-args", "tests", *removed_flag_tokens(flag))


@step(r"I scan that source")
def when_scan(m, params):
    ctx.run(ctx.source_path, "--scan")


# ── Then steps ────────────────────────────────────────────────────────────────


@step(r'the output line "([^"]+)" is printed')
def then_output_line(m, params):
    assert_stdout_contains(ctx.cli_result, step_param(m, params, "output_line"))


@step(r'the command exits with status "(\d+)"')
def then_exit_status(m, params):
    assert_exit_status(ctx.cli_result, int(step_param(m, params, "exit")))


@step(r'the output names the refusal of "([^"]*)"')
def then_names_refusal(m, params):
    assert_output_contains(ctx.cli_result, removed_flag_refusal(step_param(m, params, "flag")))


@step(r"no partition counts are printed")
def then_no_partition_counts(m, params):
    assert_no_partition_counts(ctx.cli_result)


@step(r'the first run of the tests saw the "([^"]*)" core')
def then_first_core(m, params):
    expected = step_param(m, params, "core")
    assert ctx.core_record is not None, "no core-recording test was written"
    assert first_recorded_core(ctx.core_record) == expected


@step(r"the source file is byte-for-byte unchanged")
def then_source_unchanged(m, params):
    with open(ctx.source_path, "rb") as f:
        assert f.read() == ctx.source_bytes


@step(r'no "\.mutate4py\.bak" file is left behind')
def then_no_bak_file(m, params):
    assert_no_backup_beside(ctx.source_path)
