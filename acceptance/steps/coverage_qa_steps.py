"""Step handlers for features/coverage_qa.feature (F3 QA — CLI-only)."""

import os
import shlex
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from acceptance.steps.coverage_helpers import (
    assert_baseline_scan,
    assert_exit_nonzero,
    assert_exit_zero,
    assert_stdout_contains,
    assert_stdout_not_contains,
    make_calc_source,
    make_lcov,
    make_lcov_brda_only,
    make_lcov_da_zero,
    make_lcov_single_da,
    make_noop_script,
    step_param,
    substitute_qa_cmd_placeholders,
    write_counter_script,
)
from acceptance.steps.step_lib import make_registry

STEP_HANDLERS, step, run_step = make_registry()


def _run_mutate4py(cwd: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "mutate4py"] + list(args),
        capture_output=True,
        text=True,
        cwd=cwd,
    )


class QAContext:
    def __init__(self):
        self.tmpdir: str | None = None
        self.calc_path: str | None = None
        self.calc_content: str | None = None
        self.calc_abspath: str | None = None
        self.bytes_before: bytes | None = None
        self.cli_result: subprocess.CompletedProcess | None = None
        self.cov_cmd: str | None = None

    def td(self) -> str:
        if self.tmpdir is None:
            self.tmpdir = tempfile.mkdtemp()
        return self.tmpdir


ctx = QAContext()


# ── Background ────────────────────────────────────────────────────────────────


@step(r"a temp working directory the QA agent owns and tears down")
def given_qa_tmpdir(m, params):
    # Reset context for each scenario
    ctx.tmpdir = tempfile.mkdtemp()
    ctx.calc_path = None
    ctx.calc_content = None
    ctx.calc_abspath = None
    ctx.bytes_before = None
    ctx.cli_result = None
    ctx.cov_cmd = None


@step(
    r'a Python source fixture "calc\.py" with exactly one mutation site per line on "([^"]+)"'
)
def given_calc_fixture(m, params):
    d = ctx.td()
    src = make_calc_source(step_param(m, params, "lines"))
    ctx.calc_path = os.path.join(d, "calc.py")
    ctx.calc_content = src
    ctx.calc_abspath = os.path.abspath(ctx.calc_path)
    with open(ctx.calc_path, "w") as f:
        f.write(src)


@step(r'the baseline "mutate4py calc\.py --scan" reports "Total mutation sites: (\d+)"')
def given_baseline_scan_step(m, params):
    assert_baseline_scan(
        _run_mutate4py(ctx.td(), ctx.calc_path, "--scan"),
        int(step_param(m, params, "count")),
    )


# ── Given steps ───────────────────────────────────────────────────────────────


@step(
    r'a hand-written LCOV "cov\.info" with SF matching "calc\.py" and DA hits on lines "([^"]*)"'
)
def given_lcov_da_lines(m, params):
    d = ctx.td()
    covered = {
        int(n.strip()) for n in step_param(m, params, "covered").split(",") if n.strip()
    }
    with open(os.path.join(d, "cov.info"), "w") as f:
        f.write(make_lcov(ctx.calc_path, covered))


@step(
    r'a hand-written LCOV "cov\.info" with SF matching "calc\.py" and the record "DA:5,0"'
)
def given_lcov_da_zero(m, params):
    d = ctx.td()
    with open(os.path.join(d, "cov.info"), "w") as f:
        f.write(make_lcov_da_zero(ctx.calc_path, 5))


@step(
    r'a hand-written LCOV "cov\.info" with SF matching "calc\.py" containing only "BRDA:5,0,0,1" for line 5'
)
def given_lcov_only_brda(m, params):
    d = ctx.td()
    with open(os.path.join(d, "cov.info"), "w") as f:
        f.write(make_lcov_brda_only(ctx.calc_path, 5))


@step(r'a hand-written LCOV "cov\.info" whose SF is "([^"]+)" with DA hits on line 5')
def given_lcov_sf(m, params):
    sf_key = params.get("sfPath") or m.group(1)
    d = ctx.td()
    sf = sf_key if not sf_key == "calc.py" else "calc.py"
    with open(os.path.join(d, "cov.info"), "w") as f:
        f.write(make_lcov_single_da(sf, 5))


@step(
    r'a coverage command that appends one byte to "cov-runs\.log" and writes "cov\.info" with DA hits on line 5'
)
def given_cov_cmd_sentinel(m, params):
    d = ctx.td()
    script = os.path.join(d, "run_cov.sh")
    write_counter_script(
        script,
        os.path.join(d, "cov-runs.log"),
        os.path.join(d, "coverage.lcov"),
        make_lcov_single_da(ctx.calc_path, 5),
    )
    ctx.cov_cmd = script


@step(
    r'a hand-written LCOV at the default path "coverage\.lcov" with SF matching "calc\.py" and DA hits on line 5'
)
def given_default_lcov(m, params):
    d = ctx.td()
    lcov_text = make_lcov(ctx.calc_path, {5})
    with open(os.path.join(d, "coverage.lcov"), "w") as f:
        f.write(lcov_text)


@step(r'there is no readable LCOV at "([^"]+)"')
def given_no_lcov(m, params):
    d = ctx.td()
    p = os.path.join(d, step_param(m, params, "missing"))
    if os.path.exists(p):
        os.remove(p)


@step(
    r'each referenced file in "([^"]+)" exists so the failure is the exclusivity check'
)
def given_files_exist_for_exclusivity(m, params):
    flags_str = step_param(m, params, "flags")
    d = ctx.td()
    dummy_lcov = make_lcov(ctx.calc_path, {5})
    for fname in ("cov.info", "coverage.lcov"):
        p = os.path.join(d, fname)
        if not os.path.exists(p):
            with open(p, "w") as f:
                f.write(dummy_lcov)
    if "CMD" in flags_str:
        ctx.cov_cmd = make_noop_script(os.path.join(d, "noop_cov.sh"))


@step(r'the bytes of "calc\.py" are recorded before the run')
def given_record_bytes(m, params):
    with open(ctx.calc_path, "rb") as f:
        ctx.bytes_before = f.read()


# ── When steps ────────────────────────────────────────────────────────────────


@step(r'the QA agent runs "mutate4py ([^"]+)"')
def when_qa_runs(m, params):
    d = ctx.td()
    cmd_str = substitute_qa_cmd_placeholders(
        step_param(m, params, "cmd"), d, ctx.cov_cmd, ctx.calc_path
    )
    args = shlex.split(cmd_str)
    if args[0] == "mutate4py":
        args = args[1:]
    ctx.cli_result = _run_mutate4py(d, *args)


# ── Then steps ────────────────────────────────────────────────────────────────


@step(r'stdout contains "([^"]+)"')
def then_stdout_contains(m, params):
    assert_stdout_contains(ctx.cli_result, step_param(m, params, "text"))


@step(r'stdout does not contain "([^"]+)"')
def then_stdout_not_contains(m, params):
    assert_stdout_not_contains(ctx.cli_result, step_param(m, params, "text"))


@step(r"the exit status is zero")
def then_exit_zero(m, params):
    assert_exit_zero(ctx.cli_result)


@step(r"the exit status is non-zero")
def then_exit_nonzero(m, params):
    assert_exit_nonzero(ctx.cli_result)


@step(r'the file "([^"]+)" is exactly one byte')
def then_file_one_byte(m, params):
    fname = step_param(m, params, "file")
    d = ctx.td()
    path = os.path.join(d, fname)
    assert os.path.exists(path), f"file {path} does not exist"
    size = os.path.getsize(path)
    assert size == 1, f"expected 1 byte in {fname}, got {size}"


@step(r"no coverage command was run")
def then_no_cov_cmd(m, params):
    # --reuse-coverage scenario: no CMD to check, just verify no counter file
    d = ctx.td()
    counter = os.path.join(d, "cov-runs.log")
    assert not os.path.exists(counter), (
        f"coverage command was unexpectedly run (counter at {counter})"
    )


@step(r'the bytes of "calc\.py" are unchanged after the run')
def then_bytes_unchanged(m, params):
    with open(ctx.calc_path, "rb") as f:
        after = f.read()
    assert after == ctx.bytes_before, (
        f"calc.py bytes changed:\nbefore={ctx.bytes_before!r}\nafter={after!r}"
    )


@step(r'no "\.mutate4py\.bak" file exists in the working directory')
def then_no_bak_file(m, params):
    d = ctx.td()
    for fname in os.listdir(d):
        assert not fname.endswith(".mutate4py.bak"), (
            f"unexpected .mutate4py.bak file: {fname}"
        )
