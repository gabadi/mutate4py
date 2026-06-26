"""Step handlers for features/coverage.feature (F3 coverage-gate)."""

import os
import stat
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from acceptance.steps.step_lib import make_registry

STEP_HANDLERS, step, run_step = make_registry()

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _run_mutate4py_in_dir(cwd: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "mutate4py"] + list(args),
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def _make_source_with_sites_on_lines(lines_str: str) -> str:
    """Return Python source with mutation sites on the given comma-separated line numbers.

    Lines 1 and 2 are blank padding; each requested line gets `x = a + b`.
    Lines in between that are not requested stay blank.
    """
    if lines_str.strip():
        site_lines = {int(n.strip()) for n in lines_str.split(",") if n.strip()}
    else:
        site_lines = set()

    max_line = max(site_lines) if site_lines else 0
    result = []
    for lineno in range(1, max_line + 1):
        if lineno in site_lines:
            result.append("x = a + b")
        else:
            result.append("")
    return "\n".join(result) + "\n"


def _lcov_for_source(source_path: str, covered_lines: set[int]) -> str:
    lines = [f"SF:{source_path}"]
    for ln in sorted(covered_lines):
        lines.append(f"DA:{ln},1")
    lines.append("end_of_record")
    return "\n".join(lines) + "\n"


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
    lines_str = params.get("lines") or m.group(1)
    # Reset context for each scenario (background step runs first)
    ctx.tmpdir = None
    ctx.source_path = None
    ctx.source_content = None
    ctx.cov_script_path = None
    ctx.cli_result = None
    ctx.cov_cmd_str = None
    d = ctx.ensure_tmpdir()
    src = _make_source_with_sites_on_lines(lines_str)
    ctx.source_path = os.path.join(d, "sample.py")
    ctx.source_content = src
    with open(ctx.source_path, "w") as f:
        f.write(src)


# ── Given steps ───────────────────────────────────────────────────────────────

@step(r'an LCOV file covering lines "([^"]*)" for that source')
def given_lcov_covering_lines(m, params):
    covered_str = params.get("covered") or m.group(1)
    d = ctx.ensure_tmpdir()
    covered = {int(n.strip()) for n in covered_str.split(",") if n.strip()}
    lcov_text = _lcov_for_source(ctx.source_path, covered)
    with open(os.path.join(d, "cov.info"), "w") as f:
        f.write(lcov_text)


@step(r'an LCOV file with the single record "DA:5,0" for that source')
def given_lcov_da_zero(m, params):
    d = ctx.ensure_tmpdir()
    lcov_text = f"SF:{ctx.source_path}\nDA:5,0\nend_of_record\n"
    with open(os.path.join(d, "cov.info"), "w") as f:
        f.write(lcov_text)


@step(r'an LCOV file whose only record for line 5 is branch data "BRDA:5,0,0,1"')
def given_lcov_only_brda(m, params):
    d = ctx.ensure_tmpdir()
    lcov_text = f"SF:{ctx.source_path}\nBRDA:5,0,0,1\nend_of_record\n"
    with open(os.path.join(d, "cov.info"), "w") as f:
        f.write(lcov_text)


@step(r'an LCOV file covering line 5 under the SF path "([^"]+)" for that source')
def given_lcov_sf_path(m, params):
    sf_key = params.get("sfPath") or m.group(1)
    d = ctx.ensure_tmpdir()

    if sf_key == "absolute-suffix":
        sf = ctx.source_path  # absolute path of source
    elif sf_key == "relative-suffix":
        sf = os.path.basename(ctx.source_path)  # just basename — suffix of abs
    else:  # unrelated-file
        sf = "/some/unrelated/other.py"

    lcov_text = f"SF:{sf}\nDA:5,1\nend_of_record\n"
    with open(os.path.join(d, "cov.info"), "w") as f:
        f.write(lcov_text)


@step(r"a coverage command that emits an LCOV file covering line 5")
def given_cov_cmd_covering_line5(m, params):
    d = ctx.ensure_tmpdir()
    counter_path = os.path.join(d, "cov_runs.log")
    lcov_path = os.path.join(d, "coverage.lcov")
    lcov_content = f"SF:{ctx.source_path}\nDA:5,1\nend_of_record\n"

    # Write a shell script so we can count invocations
    script_path = os.path.join(d, "run_cov.sh")
    with open(script_path, "w") as f:
        f.write("#!/bin/sh\n")
        f.write(f"printf 'x' >> {counter_path}\n")
        f.write(f"cat > {lcov_path} << 'LCOV_EOF'\n")
        f.write(lcov_content)
        f.write("LCOV_EOF\n")
    os.chmod(script_path, os.stat(script_path).st_mode | stat.S_IEXEC)

    ctx.cov_script_path = script_path
    ctx.cov_cmd_str = script_path


@step(r'an LCOV file at the default path "coverage.lcov" covering lines "([^"]*)" for that source')
def given_default_lcov(m, params):
    covered_str = params.get("lines") or m.group(1)
    d = ctx.ensure_tmpdir()
    covered = {int(n.strip()) for n in covered_str.split(",") if n.strip()}
    lcov_text = _lcov_for_source(ctx.source_path, covered)
    with open(os.path.join(d, "coverage.lcov"), "w") as f:
        f.write(lcov_text)


@step(r'there is no readable LCOV at "([^"]+)"')
def given_no_lcov_at(m, params):
    missing = params.get("missing") or m.group(1)
    d = ctx.ensure_tmpdir()
    path = os.path.join(d, missing)
    if os.path.exists(path):
        os.remove(path)


# ── When steps ────────────────────────────────────────────────────────────────

@step(r'I run mutate4py scanning with coverage "([^"]+)"')
def when_scan_with_coverage(m, params):
    flags_str = params.get("flags") or m.group(1)
    d = ctx.ensure_tmpdir()

    # Substitute CMD placeholder with actual command
    if "CMD" in flags_str and ctx.cov_cmd_str:
        flags_str = flags_str.replace("CMD", ctx.cov_cmd_str)

    # Substitute cov.info with absolute path
    if "cov.info" in flags_str and "--lcov" in flags_str:
        flags_str = flags_str.replace("cov.info", os.path.join(d, "cov.info"))

    import shlex
    extra_args = shlex.split(flags_str)
    ctx.cli_result = _run_mutate4py_in_dir(d, ctx.source_path, "--scan", *extra_args)


# ── Then steps ────────────────────────────────────────────────────────────────

@step(r'the output line "([^"]+)" is printed')
def then_output_line(m, params):
    line = params.get("output_line") or m.group(1)
    assert line in ctx.cli_result.stdout, (
        f"expected {line!r} in stdout:\n{ctx.cli_result.stdout}\nstderr:\n{ctx.cli_result.stderr}"
    )


@step(r"the coverage command runs exactly once")
def then_cmd_ran_once(m, params):
    _then_cmd_ran_n_times(1)


@step(r"the coverage command runs exactly (\d+) times?")
def then_cmd_ran_n(m, params):
    count_str = params.get("count") or m.group(1)
    _then_cmd_ran_n_times(int(count_str))


def _then_cmd_ran_n_times(expected: int) -> None:
    d = ctx.ensure_tmpdir()
    counter_path = os.path.join(d, "cov_runs.log")
    if expected == 0:
        assert not os.path.exists(counter_path), (
            f"expected 0 runs but counter file exists at {counter_path}"
        )
        return
    assert os.path.exists(counter_path), (
        f"expected {expected} runs but counter file missing at {counter_path}"
    )
    with open(counter_path) as f:
        content = f.read()
    assert len(content) == expected, (
        f"expected {expected} run(s), counter file has {len(content)} byte(s): {content!r}"
    )


@step(r"the command exits with a non-zero status")
def then_nonzero_exit(m, params):
    assert ctx.cli_result.returncode != 0, (
        f"expected non-zero exit, got 0\nstdout:\n{ctx.cli_result.stdout}"
    )


@step(r"no partition counts are printed")
def then_no_partition_counts(m, params):
    assert "Covered mutation sites:" not in ctx.cli_result.stdout, (
        f"Covered counts leaked into stdout:\n{ctx.cli_result.stdout}"
    )
    assert "Uncovered mutation sites:" not in ctx.cli_result.stdout, (
        f"Uncovered counts leaked into stdout:\n{ctx.cli_result.stdout}"
    )


@step(r"the source file is byte-for-byte unchanged")
def then_source_unchanged(m, params):
    with open(ctx.source_path) as f:
        current = f.read()
    assert current == ctx.source_content, (
        f"source file was modified:\nbefore={ctx.source_content!r}\nafter={current!r}"
    )


@step(r'no "\.mutate4py\.bak" file is left behind')
def then_no_bak_file(m, params):
    d = ctx.ensure_tmpdir()
    bak = ctx.source_path + ".mutate4py.bak" if ctx.source_path else ""
    assert not os.path.exists(bak), f".mutate4py.bak unexpectedly exists at {bak}"
    # Also check tmpdir broadly
    for fname in os.listdir(d):
        assert not fname.endswith(".mutate4py.bak"), f"unexpected bak file: {fname}"
