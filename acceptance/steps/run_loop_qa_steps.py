"""Step handlers for features/run-loop_qa.feature (F4 QA — end-to-end CLI)."""

import os
import subprocess
import sys
import tempfile
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from acceptance.steps.run_loop_qa_helpers import (
    BODY_ALWAYS_FAIL,
    BODY_ALWAYS_PASS,
    all_killed_body,
    make_lcov,
    mutated_run_exits_nonzero_body,
    mutated_run_sleeps_past_timeout_body,
    n_survivors_body,
    one_timeout_rest_killed_body,
    write_test,
)
from acceptance.steps.step_lib import make_registry

STEP_HANDLERS, step, run_step = make_registry()

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# ── calc.py fixture: two mutation sites on lines 3 and 7 ──────────────────────
# Line 3: `return a > b` in function calc1
# Line 7: `return c > d` in function calc2
CALC_PY = textwrap.dedent("""\
    # calc.py — QA fixture for F4 run-loop acceptance
    def calc1(a, b):
        return a > b

    # spacer line 5
    def calc2(c, d):
        return c > d
""")


def _run_cmd(cmd: list[str], cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)


class QAContext:
    def __init__(self):
        self.tmpdir: str | None = None
        self.calc_path: str | None = None
        self.lcov_path: str | None = None
        self.test_script: str | None = None
        self.cli_result: subprocess.CompletedProcess | None = None
        self.prior_body: str | None = None


ctx = QAContext()


def _reset():
    ctx.tmpdir = None
    ctx.calc_path = None
    ctx.lcov_path = None
    ctx.test_script = None
    ctx.cli_result = None
    ctx.prior_body = None


def _tmpdir() -> str:
    if ctx.tmpdir is None:
        ctx.tmpdir = tempfile.mkdtemp()
    return ctx.tmpdir


# ── Background ────────────────────────────────────────────────────────────────


@step(r"a temp working directory the QA agent owns and tears down")
def given_tmpdir(m, params):
    _reset()
    _tmpdir()


@step(
    r'a Python source fixture "calc\.py" with covered mutation sites on lines "([^"]*)"'
)
def given_calc_fixture(m, params):
    lines_str = params.get("3,7") or m.group(1)
    d = _tmpdir()
    ctx.calc_path = os.path.join(d, "calc.py")
    with open(ctx.calc_path, "w") as f:
        f.write(CALC_PY)


@step(
    r'a hand-written LCOV "([^"]*)" with SF matching "calc\.py" and DA hits on lines "([^"]*)"'
)
def given_lcov_fixture(m, params):
    lcov_name = params.get("cov.info") or m.group(1)
    lines_str = params.get("3,7") or m.group(2)
    d = _tmpdir()
    covered = [int(x.strip()) for x in lines_str.split(",") if x.strip()]
    ctx.lcov_path = os.path.join(d, lcov_name)
    with open(ctx.lcov_path, "w") as f:
        f.write(make_lcov(ctx.calc_path, covered))


@step(r"a fake pytest test the QA agent scripts per outcome")
def given_test_script(m, params):
    d = _tmpdir()
    tests_dir = os.path.join(d, "tests")
    os.makedirs(tests_dir, exist_ok=True)
    ctx.test_script = os.path.join(tests_dir, "test_qa.py")
    # Default: always pass; individual scenario Given steps will override
    write_test(ctx.test_script, BODY_ALWAYS_PASS)


# ── Scenario-specific Given steps ────────────────────────────────────────────


@step(r'the fake pytest test makes the mutated run "([^"]*)" while the baseline passes')
def given_mutated_outcome(m, params):
    outcome = params.get("outcome") or m.group(1)
    calc_path = ctx.calc_path
    if outcome == "exit nonzero":
        body = mutated_run_exits_nonzero_body(calc_path)
    elif outcome == "exit zero":
        body = BODY_ALWAYS_PASS
    elif outcome == "sleep past timeout":
        body = mutated_run_sleeps_past_timeout_body(calc_path)
    else:
        raise ValueError(f"Unknown outcome: {outcome}")
    write_test(ctx.test_script, body)


@step(
    r"the fake pytest test makes one mutant sleep past the timeout and the rest exit nonzero"
)
def given_one_timeout_rest_killed(m, params):
    d = _tmpdir()
    # Counter to track mutant number; first mutant times out, rest are killed
    counter_path = os.path.join(d, "mutant_counter.txt")
    with open(counter_path, "w") as f:
        f.write("0")
    write_test(ctx.test_script, one_timeout_rest_killed_body(counter_path))


@step(
    r'the fake pytest test makes "(\d+)" of the 2 mutants exit zero and the rest exit nonzero'
)
def given_n_survivors(m, params):
    survived_count = params.get("survivedCount") or m.group(1)
    n = int(survived_count)
    d = _tmpdir()
    counter_path = os.path.join(d, "mutant_counter.txt")
    with open(counter_path, "w") as f:
        f.write("0")
    write_test(ctx.test_script, n_survivors_body(counter_path, n))


@step(r"the fake pytest test exits nonzero on the unmutated baseline run")
def given_baseline_fails(m, params):
    # Always fails, including the baseline
    write_test(ctx.test_script, BODY_ALWAYS_FAIL)


@step(r"the fake pytest test exits nonzero for every mutant")
def given_all_killed(m, params):
    d = _tmpdir()
    counter_path = os.path.join(d, "mutant_counter.txt")
    with open(counter_path, "w") as f:
        f.write("0")
    write_test(ctx.test_script, all_killed_body(counter_path))


@step(r'the bytes of "calc\.py" before any manifest footer are recorded')
def given_record_prior_body(m, params):
    from mutate4py._manifest import strip_manifest

    with open(ctx.calc_path) as f:
        src = f.read()
    ctx.prior_body = strip_manifest(src)


@step(
    r'a "\.mutate4py\.bak" file holding a known prior source body exists in the working directory'
)
def given_bak_exists(m, params):
    bak_path = ctx.calc_path + ".bak"
    with open(bak_path, "w") as f:
        f.write(CALC_PY)
    ctx.prior_body = CALC_PY


@step(r'"calc\.py" on disk currently holds a leftover spliced mutant')
def given_mutant_spliced(m, params):
    # Splice a mutant into calc.py to simulate an interrupted run
    mutated = CALC_PY.replace("a > b", "a >= b")
    with open(ctx.calc_path, "w") as f:
        f.write(mutated)


@step(
    r'a hand-written LCOV at the default path "coverage\.lcov" with DA hits on lines "([^"]*)"'
)
def given_reuse_lcov(m, params):
    lines_str = params.get("3,7") or m.group(1)
    d = _tmpdir()
    covered = [int(x.strip()) for x in lines_str.split(",") if x.strip()]
    lcov_path = os.path.join(d, "coverage.lcov")
    with open(lcov_path, "w") as f:
        f.write(make_lcov(ctx.calc_path, covered))


# ── When steps ────────────────────────────────────────────────────────────────


@step(r'the QA agent runs "([^"]*)"')
def when_qa_runs(m, params):
    cmd_str = params.get("cmd") or m.group(1)
    # Parse the command string keeping relative paths as-is (run from tmpdir)
    parts = cmd_str.split()
    d = _tmpdir()
    resolved = [part for part in parts if part != "mutate4py"]  # handled via uv run
    ctx.cli_result = subprocess.run(
        ["uv", "run", "mutate4py"] + resolved,
        capture_output=True,
        text=True,
        cwd=d,
    )


# ── Then steps ────────────────────────────────────────────────────────────────


@step(r'stdout contains a line matching "\[<n>/<total>\] (\w+) line " for that mutant')
def then_progress_line_present(m, params):
    status = m.group(1)
    stdout = ctx.cli_result.stdout
    import re as _re

    progress_lines = [
        l
        for l in stdout.splitlines()
        if _re.match(rf"\[\d+/\d+\] {_re.escape(status)} line ", l)
    ]
    assert progress_lines, (
        f"No progress lines with status '{status}' found in stdout:\n{stdout}"
    )


@step(r"the exit status is zero")
def then_exit_zero(m, params):
    assert ctx.cli_result.returncode == 0, (
        f"Expected exit 0, got {ctx.cli_result.returncode}\n"
        f"stdout:\n{ctx.cli_result.stdout}\n"
        f"stderr:\n{ctx.cli_result.stderr}"
    )


@step(r'stdout contains "([^"]*)"')
def then_stdout_contains(m, params):
    expected = params.get("text") or m.group(1)
    assert expected in ctx.cli_result.stdout, (
        f"Expected '{expected}' in stdout:\n{ctx.cli_result.stdout}"
    )


@step(r'stdout does not contain "([^"]*)"')
def then_stdout_not_contains(m, params):
    not_expected = params.get("text") or m.group(1)
    assert not_expected not in ctx.cli_result.stdout, (
        f"Unexpected '{not_expected}' in stdout:\n{ctx.cli_result.stdout}"
    )


@step(r"the exit status is non-zero")
def then_exit_nonzero(m, params):
    assert ctx.cli_result.returncode != 0, (
        f"Expected non-zero exit, got {ctx.cli_result.returncode}\n"
        f"stdout:\n{ctx.cli_result.stdout}"
    )


@step(r'no "\.mutate4py\.bak" file exists in the working directory')
def then_no_bak_file(m, params):
    d = _tmpdir()
    bak = ctx.calc_path + ".bak"
    assert not os.path.exists(bak), f"Unexpected .bak file at: {bak}"


@step(r'stdout "([^"]*)" contain "([^"]*)"')
def then_stdout_conditional_contains(m, params):
    contains_word = params.get("containsSurvivors") or m.group(1)
    text = params.get("Survivors:") or m.group(2)
    stdout = ctx.cli_result.stdout
    if contains_word == "does":
        assert text in stdout, f"Expected '{text}' in stdout:\n{stdout}"
    else:  # "does not"
        assert text not in stdout, f"Did not expect '{text}' in stdout:\n{stdout}"


@step(r'the body of "calc\.py" above the manifest footer is unchanged')
def then_body_unchanged(m, params):
    from mutate4py._manifest import strip_manifest

    with open(ctx.calc_path) as f:
        content = f.read()
    body = strip_manifest(content)
    assert body.strip() == ctx.prior_body.strip(), (
        f"Body changed!\nExpected:\n{ctx.prior_body}\nGot:\n{body}"
    )


@step(r'the body of "calc\.py" above the manifest footer matches the prior source body')
def then_body_matches_prior(m, params):
    from mutate4py._manifest import strip_manifest

    with open(ctx.calc_path) as f:
        content = f.read()
    body = strip_manifest(content)
    assert body.strip() == ctx.prior_body.strip(), (
        f"Body does not match prior!\nExpected:\n{ctx.prior_body}\nGot:\n{body}"
    )


@step(
    r'"calc\.py" ends with a "mutate4py-manifest-begin" / "mutate4py-manifest-end" footer'
)
def then_manifest_footer(m, params):
    with open(ctx.calc_path) as f:
        content = f.read()
    assert "mutate4py-manifest-begin" in content, f"No manifest footer:\n{content}"
    assert "mutate4py-manifest-end" in content, f"No manifest footer end:\n{content}"


@step(r'that line appears before "Mutation run: calc\.py" in stdout')
def then_stale_warning_before_header(m, params):
    stdout = ctx.cli_result.stdout
    assert "Reusing existing coverage" in stdout, (
        f"Expected stale warning in:\n{stdout}"
    )
    assert "Mutation run: " in stdout, f"Expected 'Mutation run:' in:\n{stdout}"
    warn_pos = stdout.index("Reusing existing coverage")
    header_pos = stdout.index("Mutation run: ")
    assert warn_pos < header_pos, (
        "Stale warning must appear before 'Mutation run:' header"
    )
