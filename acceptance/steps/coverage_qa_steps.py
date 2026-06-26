"""Step handlers for features/coverage_qa.feature (F3 QA — CLI-only)."""

import os
import shlex
import stat
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from acceptance.steps.step_lib import make_registry

STEP_HANDLERS, step, run_step = make_registry()

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _run_mutate4py(cwd: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "mutate4py"] + list(args),
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def _make_calc_source(lines_str: str) -> str:
    """Python source with exactly one mutation site per listed line."""
    site_lines = {int(n.strip()) for n in lines_str.split(",") if n.strip()}
    max_line = max(site_lines) if site_lines else 0
    rows = []
    for ln in range(1, max_line + 1):
        rows.append("x = a > b" if ln in site_lines else "")
    return "\n".join(rows) + "\n"


def _lcov(sf: str, da_lines: set[int]) -> str:
    parts = [f"SF:{sf}"]
    for ln in sorted(da_lines):
        parts.append(f"DA:{ln},1")
    parts.append("end_of_record")
    return "\n".join(parts) + "\n"


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


@step(r'a Python source fixture "calc\.py" with exactly one mutation site per line on "([^"]+)"')
def given_calc_fixture(m, params):
    lines_str = params.get("lines") or m.group(1)
    d = ctx.td()
    src = _make_calc_source(lines_str)
    ctx.calc_path = os.path.join(d, "calc.py")
    ctx.calc_content = src
    ctx.calc_abspath = os.path.abspath(ctx.calc_path)
    with open(ctx.calc_path, "w") as f:
        f.write(src)


@step(r'the baseline "mutate4py calc\.py --scan" reports "Total mutation sites: (\d+)"')
def given_baseline_scan(m, params):
    count_str = params.get("count") or m.group(1)
    expected = int(count_str)
    d = ctx.td()
    result = _run_mutate4py(d, ctx.calc_path, "--scan")
    assert result.returncode == 0, f"baseline scan failed:\n{result.stderr}"
    assert f"Total mutation sites: {expected}" in result.stdout, (
        f"baseline expected {expected} sites; got:\n{result.stdout}"
    )


# ── Given steps ───────────────────────────────────────────────────────────────

@step(r'a hand-written LCOV "cov\.info" with SF matching "calc\.py" and DA hits on lines "([^"]*)"')
def given_lcov_da_lines(m, params):
    covered_str = params.get("covered") or m.group(1)
    d = ctx.td()
    covered = {int(n.strip()) for n in covered_str.split(",") if n.strip()}
    lcov_text = _lcov(ctx.calc_path, covered)
    with open(os.path.join(d, "cov.info"), "w") as f:
        f.write(lcov_text)


@step(r'a hand-written LCOV "cov\.info" with SF matching "calc\.py" and the record "DA:5,0"')
def given_lcov_da_zero(m, params):
    d = ctx.td()
    lcov_text = f"SF:{ctx.calc_path}\nDA:5,0\nend_of_record\n"
    with open(os.path.join(d, "cov.info"), "w") as f:
        f.write(lcov_text)


@step(r'a hand-written LCOV "cov\.info" with SF matching "calc\.py" containing only "BRDA:5,0,0,1" for line 5')
def given_lcov_only_brda(m, params):
    d = ctx.td()
    lcov_text = f"SF:{ctx.calc_path}\nBRDA:5,0,0,1\nend_of_record\n"
    with open(os.path.join(d, "cov.info"), "w") as f:
        f.write(lcov_text)


@step(r'a hand-written LCOV "cov\.info" whose SF is "([^"]+)" with DA hits on line 5')
def given_lcov_sf(m, params):
    sf_key = params.get("sfPath") or m.group(1)
    d = ctx.td()

    if sf_key == "calc.py":
        # bare basename — suffix match
        sf = "calc.py"
    elif sf_key.startswith("other/"):
        sf = sf_key  # unrelated path
    else:
        sf = sf_key

    lcov_text = f"SF:{sf}\nDA:5,1\nend_of_record\n"
    with open(os.path.join(d, "cov.info"), "w") as f:
        f.write(lcov_text)


@step(r'a coverage command that appends one byte to "cov-runs\.log" and writes "cov\.info" with DA hits on line 5')
def given_cov_cmd_sentinel(m, params):
    d = ctx.td()
    counter = os.path.join(d, "cov-runs.log")
    lcov_path = os.path.join(d, "coverage.lcov")
    lcov_content = f"SF:{ctx.calc_path}\nDA:5,1\nend_of_record\n"

    script = os.path.join(d, "run_cov.sh")
    with open(script, "w") as f:
        f.write("#!/bin/sh\n")
        f.write(f"printf 'x' >> {counter}\n")
        f.write(f"cat > {lcov_path} << 'LCOV_EOF'\n")
        f.write(lcov_content)
        f.write("LCOV_EOF\n")
    os.chmod(script, os.stat(script).st_mode | stat.S_IEXEC)
    ctx.cov_cmd = script


@step(r'a hand-written LCOV at the default path "coverage\.lcov" with SF matching "calc\.py" and DA hits on line 5')
def given_default_lcov(m, params):
    d = ctx.td()
    lcov_text = _lcov(ctx.calc_path, {5})
    with open(os.path.join(d, "coverage.lcov"), "w") as f:
        f.write(lcov_text)


@step(r'there is no readable LCOV at "([^"]+)"')
def given_no_lcov(m, params):
    missing = params.get("missing") or m.group(1)
    d = ctx.td()
    p = os.path.join(d, missing)
    if os.path.exists(p):
        os.remove(p)


@step(r'each referenced file in "([^"]+)" exists so the failure is the exclusivity check')
def given_files_exist_for_exclusivity(m, params):
    flags_str = params.get("flags") or m.group(1)
    d = ctx.td()
    # Create cov.info and coverage.lcov so missing-file errors don't fire first
    dummy_lcov = _lcov(ctx.calc_path, {5})
    for fname in ("cov.info", "coverage.lcov"):
        p = os.path.join(d, fname)
        if not os.path.exists(p):
            with open(p, "w") as f:
                f.write(dummy_lcov)
    # If CMD is in flags, make a no-op script
    if "CMD" in flags_str:
        noop = os.path.join(d, "noop_cov.sh")
        with open(noop, "w") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(noop, os.stat(noop).st_mode | stat.S_IEXEC)
        ctx.cov_cmd = noop


@step(r'the bytes of "calc\.py" are recorded before the run')
def given_record_bytes(m, params):
    with open(ctx.calc_path, "rb") as f:
        ctx.bytes_before = f.read()


# ── When steps ────────────────────────────────────────────────────────────────

@step(r'the QA agent runs "mutate4py ([^"]+)"')
def when_qa_runs(m, params):
    cmd_str = params.get("cmd") or m.group(1)
    d = ctx.td()

    # Replace CMD with actual script
    if "CMD" in cmd_str and ctx.cov_cmd:
        cmd_str = cmd_str.replace("CMD", ctx.cov_cmd)

    # Replace '<that command>' with actual script
    if "'<that command>'" in cmd_str and ctx.cov_cmd:
        cmd_str = cmd_str.replace("'<that command>'", ctx.cov_cmd)

    # Replace <abspath>/calc.py with absolute path to source (before calc.py replacement)
    if "<abspath>/calc.py" in cmd_str:
        cmd_str = cmd_str.replace("<abspath>/calc.py", ctx.calc_path)
    elif "calc.py" in cmd_str:
        # Replace bare calc.py with absolute path
        cmd_str = cmd_str.replace("calc.py", ctx.calc_path)

    # Replace cov.info with absolute path if --lcov present
    if "--lcov cov.info" in cmd_str:
        cmd_str = cmd_str.replace("--lcov cov.info", f"--lcov {os.path.join(d, 'cov.info')}")

    args = shlex.split(cmd_str)
    # args[0] is "mutate4py", skip it
    if args[0] == "mutate4py":
        args = args[1:]

    ctx.cli_result = _run_mutate4py(d, *args)


# ── Then steps ────────────────────────────────────────────────────────────────

@step(r'stdout contains "([^"]+)"')
def then_stdout_contains(m, params):
    text = params.get("text") or m.group(1)
    assert text in ctx.cli_result.stdout, (
        f"expected {text!r} in stdout:\n{ctx.cli_result.stdout}\nstderr:\n{ctx.cli_result.stderr}"
    )


@step(r'stdout does not contain "([^"]+)"')
def then_stdout_not_contains(m, params):
    text = params.get("text") or m.group(1)
    assert text not in ctx.cli_result.stdout, (
        f"unexpected {text!r} found in stdout:\n{ctx.cli_result.stdout}"
    )


@step(r"the exit status is zero")
def then_exit_zero(m, params):
    assert ctx.cli_result.returncode == 0, (
        f"expected exit 0, got {ctx.cli_result.returncode}\n"
        f"stdout:\n{ctx.cli_result.stdout}\nstderr:\n{ctx.cli_result.stderr}"
    )


@step(r"the exit status is non-zero")
def then_exit_nonzero(m, params):
    assert ctx.cli_result.returncode != 0, (
        f"expected non-zero exit, got 0\nstdout:\n{ctx.cli_result.stdout}"
    )


@step(r'the file "([^"]+)" is exactly one byte')
def then_file_one_byte(m, params):
    fname = params.get("file") or m.group(1)
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
