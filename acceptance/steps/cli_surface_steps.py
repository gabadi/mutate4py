"""Step handlers for features/cli-surface.feature (F5 CLI surface)."""

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from acceptance.steps.cli_surface_helpers import (
    accepted_flags_args,
    assert_accepted,
    assert_all_reported,
    assert_baseline_run,
    assert_dispatched_to,
    assert_exit_status,
    assert_names_interpreters,
    assert_no_analysis,
    assert_no_baseline_run,
    assert_nonzero_exit,
    assert_only_reported,
    assert_option_accepted,
    assert_usage_error,
    assert_usage_lists_max_workers,
    assert_usage_printed,
    assert_worker_count,
    assert_zero_exit,
    REACHING_TEST,
    assert_bytes_unchanged,
    assert_error_printed,
    assert_no_backup,
    default_source,
    rejected_args,
    described_args,
    exclude_run_args,
    require_result,
    run_with_running_interpreter,
    single_flag_args,
    two_flag_args,
    two_target_run_args,
    write_baseline_sentinel,
    write_placeholder_venv,
    write_pyproject,
)
from acceptance.steps.step_lib import make_registry

STEP_HANDLERS, step, run_step = make_registry()

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _run_mutate4py(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "mutate4py"] + list(args),
        capture_output=True,
        text=True,
        cwd=cwd or REPO_ROOT,
    )


class Context:
    def __init__(self):
        self.tmpdir: str | None = None
        self.src_path: str | None = None
        self.src_bytes_before: bytes | None = None
        self.cli_result: subprocess.CompletedProcess | None = None
        self.dispatch_max_workers: int | None = None
        self.dir_path: str | None = None
        self.file_pair: tuple[str, str] | None = None
        self.foreign_env: str | None = None
        self.sentinel_marker: str | None = None

    def reset(self):
        self.tmpdir = None
        self.src_path = None
        self.src_bytes_before = None
        self.cli_result = None
        self.dispatch_max_workers = None
        self.dir_path = None
        self.file_pair = None
        self.foreign_env = None
        self.sentinel_marker = None

    def ensure_tmpdir(self) -> str:
        if self.tmpdir is None:
            self.tmpdir = tempfile.mkdtemp()
        return self.tmpdir

    def ensure_src(self) -> str:
        if self.src_path is None:
            d = self.ensure_tmpdir()
            self.src_path = os.path.join(d, "sample.py")
            with open(self.src_path, "w") as f:
                f.write(default_source())
            with open(self.src_path, "rb") as f:
                self.src_bytes_before = f.read()
        return self.src_path

    def ensure_passing_tests(self) -> None:
        """Write a passing pytest test that reaches the source's site (and the
        empty conftest.py that puts the project root on sys.path) into tmpdir, so
        the flag/two-flag/accepted-flags helpers below can reach the real run
        loop with --pytest-args "-q tests"."""
        root = self.ensure_tmpdir()
        tests_dir = os.path.join(root, "tests")
        os.makedirs(tests_dir, exist_ok=True)
        with open(os.path.join(root, "conftest.py"), "w") as f:
            f.write("")
        with open(os.path.join(tests_dir, "test_ok.py"), "w") as f:
            f.write(REACHING_TEST)

    def make_dir_with(self, *names: str) -> str:
        d = os.path.join(self.ensure_tmpdir(), "pkg")
        os.makedirs(d, exist_ok=True)
        for name in names:
            with open(os.path.join(d, name), "w") as f:
                f.write(default_source())
        self.dir_path = d
        return d

    def require_dir(self) -> str:
        assert self.dir_path is not None, "No directory created"
        return self.dir_path

    def make_two_files(self, name1: str, name2: str) -> tuple[str, str]:
        d = self.ensure_tmpdir()
        p1 = os.path.join(d, name1)
        p2 = os.path.join(d, name2)
        for p in (p1, p2):
            with open(p, "w") as f:
                f.write(default_source())
        self.file_pair = (p1, p2)
        return self.file_pair

    def require_file_pair(self) -> tuple[str, str]:
        assert self.file_pair is not None, "No file pair created"
        return self.file_pair


ctx = Context()


# ── Background ────────────────────────────────────────────────────────────────


@step(r"an existing Python source file with discovered mutation sites")
def given_source_with_sites(m, params):
    ctx.reset()
    ctx.ensure_src()


@step(r'a directory holding "(.*)" and "(.*)"')
def given_directory_holding(m, params):
    ctx.make_dir_with(m.group(1).strip(), m.group(2).strip())


@step(r'two Python source files "(.*)" and "(.*)" without a manifest')
def given_two_files(m, params):
    ctx.reset()
    ctx.make_two_files(m.group(1).strip(), m.group(2).strip())


# ── When steps ────────────────────────────────────────────────────────────────


@step(r'I run mutate4py with the flag "(.*)"')
def when_run_with_flag(m, params):
    ctx.ensure_passing_tests()
    args = single_flag_args(m.group(1), ctx.ensure_src())
    ctx.cli_result = _run_mutate4py(*args, cwd=ctx.ensure_tmpdir())


@step(r'I run mutate4py with a trailing "(.*)" and no value')
def when_run_with_trailing_flag(m, params):
    ctx.cli_result = _run_mutate4py(ctx.ensure_src(), m.group(1).strip(), cwd=ctx.ensure_tmpdir())


@step(r'I run mutate4py with "(.*)" and "(.*)"')
def when_run_with_two_flags(m, params):
    ctx.ensure_passing_tests()
    args = two_flag_args(m.group(1).strip(), m.group(2).strip(), ctx.ensure_src())
    ctx.cli_result = _run_mutate4py(*args, cwd=ctx.ensure_tmpdir())


@step(r'I run mutate4py on that directory with "(.*)" excluding "(.*)"')
def when_run_directory_excluding(m, params):
    args = exclude_run_args(m.group(1).strip(), m.group(2).strip(), ctx.require_dir())
    ctx.cli_result = _run_mutate4py(*args, cwd=ctx.ensure_tmpdir())


@step(r'I run mutate4py on both files with "(.*)"')
def when_run_on_both_files(m, params):
    p1, p2 = ctx.require_file_pair()
    args = two_target_run_args(m.group(1).strip(), p1, p2)
    ctx.cli_result = _run_mutate4py(*args, cwd=ctx.ensure_tmpdir())


@step(r'I run mutate4py described by "(.*)"')
def when_run_described(m, params):
    args = described_args(m.group(1).strip(), ctx.ensure_src())
    ctx.cli_result = _run_mutate4py(*args, cwd=ctx.ensure_tmpdir())


@step(r'I run the rejected invocation "(.*)"')
def when_run_rejected_invocation(m, params):
    ctx.ensure_passing_tests()
    args = rejected_args(m.group(1).strip(), ctx.ensure_src())
    ctx.cli_result = _run_mutate4py(*args, cwd=ctx.ensure_tmpdir())


@step(r'I run mutate4py with the accepted flags "(.*)"')
def when_run_with_accepted_flags(m, params):
    ctx.ensure_passing_tests()
    args, _target, workers = accepted_flags_args(m.group(1).strip(), ctx.ensure_src())
    ctx.dispatch_max_workers = workers
    ctx.cli_result = _run_mutate4py(*args, cwd=ctx.ensure_tmpdir())


# ── Then steps ────────────────────────────────────────────────────────────────


@step(r'the option "(.*)" is set to "(.*)"')
def then_option_set(m, params):
    r = require_result(ctx.cli_result)
    assert_option_accepted(m.group(1).strip(), m.group(2).strip(), r.returncode, r.stderr)


@step(r"the invocation is accepted")
def then_invocation_accepted(m, params):
    r = require_result(ctx.cli_result)
    assert_accepted(r.returncode, r.stdout, r.stderr)


@step(r"the invocation is a usage error")
def then_invocation_usage_error(m, params):
    r = require_result(ctx.cli_result)
    assert_usage_error(r.returncode, r.stdout, r.stderr)


@step(r"the command exits with a non-zero status")
def then_nonzero_exit(m, params):
    assert_nonzero_exit(require_result(ctx.cli_result).returncode)


@step(r"the command exits with status zero")
def then_zero_exit(m, params):
    r = require_result(ctx.cli_result)
    assert_zero_exit(r.returncode, r.stderr)


@step(r"the printed output names the offending flag or combination")
def then_output_names_offender(m, params):
    r = require_result(ctx.cli_result)
    assert_error_printed(r.stdout + r.stderr)


@step(r"the source file is byte-identical to before the run")
def then_source_byte_identical(m, params):
    assert ctx.src_path is not None, "No source path recorded"
    with open(ctx.src_path, "rb") as f:
        assert_bytes_unchanged(ctx.src_bytes_before, f.read())


@step(r'no "\.mutate4py\.bak" file was created')
def then_no_backup_created(m, params):
    assert ctx.src_path is not None, "No source path recorded"
    assert_no_backup(ctx.src_path)


@step(r"no analysis or test run occurs")
def then_no_analysis(m, params):
    assert_no_analysis(require_result(ctx.cli_result).stdout)


@step(r"the usage summary is printed")
def then_usage_printed(m, params):
    assert_usage_printed(require_result(ctx.cli_result).stdout)


@step(r'the usage summary lists "--max-workers"')
def then_usage_lists_max_workers(m, params):
    assert_usage_lists_max_workers(require_result(ctx.cli_result).stdout)


@step(r'the run is dispatched to the "(.*)" behaviour')
def then_dispatched_to(m, params):
    r = require_result(ctx.cli_result)
    assert_dispatched_to(m.group(1).strip(), r.returncode, r.stdout, r.stderr)


@step(r'only "(.*)" is reported')
def then_only_reported(m, params):
    r = require_result(ctx.cli_result)
    assert_only_reported(r.stdout, m.group(1).strip())


@step(r'both "(.*)" and "(.*)" are reported')
def then_both_reported(m, params):
    r = require_result(ctx.cli_result)
    assert_all_reported(r.stdout, [m.group(1).strip(), m.group(2).strip()])


@step(r'the dispatcher receives a worker count of "(.*)"')
def then_dispatcher_receives_workers(m, params):
    r = require_result(ctx.cli_result)
    assert_worker_count(ctx.dispatch_max_workers, m.group(1).strip(), r.returncode, r.stderr)


# ── Project environment (cli-surface-15) ──────────────────────────────────────


@step(r'a project with a "\.venv" that the running interpreter is not')
def given_foreign_project_env(m, params):
    _prepare_project(with_env=True)


def _prepare_project(*, with_env: bool) -> None:
    ctx.reset()
    root = ctx.ensure_tmpdir()
    write_pyproject(root)
    if with_env:
        ctx.foreign_env = write_placeholder_venv(root)
    ctx.ensure_src()
    ctx.sentinel_marker = write_baseline_sentinel(root)


@step(r'I run mutate4py with the accepted flags "(.*)" from outside that environment')
def when_run_from_outside_env(m, params):
    _run_accepted_flags_from_project(m.group(1))


def _run_accepted_flags_from_project(flags: str) -> None:
    args, _target, _workers = accepted_flags_args(flags.strip(), ctx.ensure_src())
    ctx.cli_result = run_with_running_interpreter(args, cwd=ctx.ensure_tmpdir())


@step(r'the command exits with status "(\d+)"')
def then_exit_status(m, params):
    assert_exit_status(require_result(ctx.cli_result).returncode, int(m.group(1)))


@step(r"the error names the running interpreter and the project environment")
def then_error_names_interpreters(m, params):
    r = require_result(ctx.cli_result)
    assert ctx.foreign_env is not None, "no project environment fixture recorded"
    assert_names_interpreters(r.stdout + r.stderr, os.path.realpath(sys.prefix), ctx.foreign_env)


@step(r"no baseline pytest run is started")
def then_no_baseline_run(m, params):
    assert ctx.sentinel_marker is not None, "no baseline sentinel recorded"
    assert_no_baseline_run(ctx.sentinel_marker)


@step(r'a project with no "\.venv"')
def given_project_without_env(m, params):
    _prepare_project(with_env=False)


@step(r'I run mutate4py with the accepted flags "(.*)" from that project')
def when_run_from_project(m, params):
    _run_accepted_flags_from_project(m.group(1))


@step(r"a baseline pytest run is started")
def then_baseline_runs(m, params):
    assert ctx.sentinel_marker is not None, "no baseline sentinel recorded"
    assert_baseline_run(ctx.sentinel_marker)
