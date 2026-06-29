"""Step handlers for features/coverage.feature (F3 coverage-gate)."""

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from acceptance.steps.coverage_helpers import (
    assert_cmd_ran_n_times,
    assert_exit_nonzero,
    assert_stdout_contains,
    make_lcov,
    make_lcov_brda_only,
    make_lcov_da_zero,
    make_lcov_single_da,
    make_source_with_sites_on_lines,
    resolve_sf_path,
    step_param,
    substitute_cmd_placeholders,
    write_counter_script,
)
from acceptance.steps.step_lib import make_registry

STEP_HANDLERS, step, run_step = make_registry()


def _run_mutate4py_in_dir(cwd: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "mutate4py"] + list(args),
        capture_output=True,
        text=True,
        cwd=cwd,
    )


class Context:
    def __init__(self):
        self.tmpdir: str | None = None
        self.source_path: str | None = None
        self.source_content: str | None = None
        self.cov_script_path: str | None = None
        self.cli_result: subprocess.CompletedProcess | None = None
        self.cov_cmd_str: str | None = None

    def ensure_tmpdir(self) -> str:
        if self.tmpdir is None:
            self.tmpdir = tempfile.mkdtemp()
        return self.tmpdir


ctx = Context()


# ── Background ────────────────────────────────────────────────────────────────


@step(r'a Python source file with mutation sites on lines "([^"]*)"')
def given_source_with_sites(m, params):
    lines_str = step_param(m, params, "lines")
    ctx.tmpdir = None
    ctx.source_path = None
    ctx.source_content = None
    ctx.cov_script_path = None
    ctx.cli_result = None
    ctx.cov_cmd_str = None
    d = ctx.ensure_tmpdir()
    src = make_source_with_sites_on_lines(lines_str)
    ctx.source_path = os.path.join(d, "sample.py")
    ctx.source_content = src
    with open(ctx.source_path, "w") as f:
        f.write(src)


# ── Given steps ───────────────────────────────────────────────────────────────


@step(r'an LCOV file covering lines "([^"]*)" for that source')
def given_lcov_covering_lines(m, params):
    d = ctx.ensure_tmpdir()
    covered = {
        int(n.strip()) for n in step_param(m, params, "covered").split(",") if n.strip()
    }
    with open(os.path.join(d, "cov.info"), "w") as f:
        f.write(make_lcov(ctx.source_path, covered))


@step(r'an LCOV file with the single record "DA:5,0" for that source')
def given_lcov_da_zero(m, params):
    d = ctx.ensure_tmpdir()
    with open(os.path.join(d, "cov.info"), "w") as f:
        f.write(make_lcov_da_zero(ctx.source_path, 5))


@step(r'an LCOV file whose only record for line 5 is branch data "BRDA:5,0,0,1"')
def given_lcov_only_brda(m, params):
    d = ctx.ensure_tmpdir()
    with open(os.path.join(d, "cov.info"), "w") as f:
        f.write(make_lcov_brda_only(ctx.source_path, 5))


@step(r'an LCOV file covering line 5 under the SF path "([^"]+)" for that source')
def given_lcov_sf_path(m, params):
    sf_key = step_param(m, params, "sfPath")
    d = ctx.ensure_tmpdir()
    sf = (
        resolve_sf_path(sf_key, ctx.source_path)
        if sf_key != "unrelated-file"
        else "/some/unrelated/other.py"
    )
    with open(os.path.join(d, "cov.info"), "w") as f:
        f.write(make_lcov_single_da(sf, 5))


@step(r"a coverage command that emits an LCOV file covering line 5")
def given_cov_cmd_covering_line5(m, params):
    d = ctx.ensure_tmpdir()
    script_path = os.path.join(d, "run_cov.sh")
    write_counter_script(
        script_path,
        os.path.join(d, "cov_runs.log"),
        os.path.join(d, "coverage.lcov"),
        make_lcov_single_da(ctx.source_path, 5),
    )
    ctx.cov_script_path = script_path
    ctx.cov_cmd_str = script_path


@step(
    r'an LCOV file at the default path "coverage.lcov" covering lines "([^"]*)" for that source'
)
def given_default_lcov(m, params):
    d = ctx.ensure_tmpdir()
    covered = {
        int(n.strip()) for n in step_param(m, params, "lines").split(",") if n.strip()
    }
    with open(os.path.join(d, "coverage.lcov"), "w") as f:
        f.write(make_lcov(ctx.source_path, covered))


@step(r'there is no readable LCOV at "([^"]+)"')
def given_no_lcov_at(m, params):
    d = ctx.ensure_tmpdir()
    path = os.path.join(d, step_param(m, params, "missing"))
    if os.path.exists(path):
        os.remove(path)


# ── When steps ────────────────────────────────────────────────────────────────


@step(r'I run mutate4py scanning with coverage "([^"]+)"')
def when_scan_with_coverage(m, params):
    import shlex

    d = ctx.ensure_tmpdir()
    flags_str = step_param(m, params, "flags")
    flags_str = substitute_cmd_placeholders(flags_str, d, ctx.cov_cmd_str)
    extra_args = shlex.split(flags_str)
    ctx.cli_result = _run_mutate4py_in_dir(d, ctx.source_path, "--scan", *extra_args)


# ── Then steps ────────────────────────────────────────────────────────────────


@step(r'the output line "([^"]+)" is printed')
def then_output_line(m, params):
    assert_stdout_contains(ctx.cli_result, step_param(m, params, "output_line"))


@step(r"the coverage command runs exactly once")
def then_cmd_ran_once(m, params):
    assert_cmd_ran_n_times(ctx.ensure_tmpdir(), 1)


@step(r"the coverage command runs exactly (\d+) times?")
def then_cmd_ran_n(m, params):
    assert_cmd_ran_n_times(ctx.ensure_tmpdir(), int(step_param(m, params, "count")))


@step(r"the command exits with a non-zero status")
def then_nonzero_exit(m, params):
    assert_exit_nonzero(ctx.cli_result)


@step(r"no partition counts are printed")
def then_no_partition_counts(m, params):
    assert "Covered mutation sites:" not in ctx.cli_result.stdout
    assert "Uncovered mutation sites:" not in ctx.cli_result.stdout


@step(r"the source file is byte-for-byte unchanged")
def then_source_unchanged(m, params):
    with open(ctx.source_path) as f:
        current = f.read()
    assert current == ctx.source_content


@step(r'no "\.mutate4py\.bak" file is left behind')
def then_no_bak_file(m, params):
    d = ctx.ensure_tmpdir()
    bak = ctx.source_path + ".mutate4py.bak" if ctx.source_path else ""
    assert not os.path.exists(bak)
    for fname in os.listdir(d):
        assert not fname.endswith(".mutate4py.bak")
