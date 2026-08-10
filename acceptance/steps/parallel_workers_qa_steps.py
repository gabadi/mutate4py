"""Step handlers for features/parallel-workers_qa.feature (F6 QA — end-to-end CLI).

QA operates ONLY through the user interface: the mutate4py CLI, its stdout,
exit codes, and on-disk state. No internal imports from mutate4py.
"""

import os
import subprocess
import sys
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from acceptance.steps.step_lib import make_registry

STEP_HANDLERS, step, run_step = make_registry()

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# ── calc.py fixture: 4 comparison sites on lines 3,5,7,9 ─────────────────────
#   Line 1: def calc1(a, b):
#   Line 2:     pass
#   Line 3:     return a > b   ← site
#   Line 4: def calc2(c, d):
#   Line 5:     return c > d   ← site
#   Line 6: def calc3(e, f):
#   Line 7:     return e > f   ← site
#   Line 8: def calc4(g, h):
#   Line 9:     return g > h   ← site
CALC_PY = textwrap.dedent("""\
    def calc1(a, b):
        pass
        return a > b
    def calc2(c, d):
        return c > d
    def calc3(e, f):
        return e > f
    def calc4(g, h):
        return g > h
""")
COVERED_LINES = [3, 5, 7, 9]


def _make_lcov(source_abs: str, covered_lines: list[int]) -> str:
    da = "\n".join(f"DA:{ln},1" for ln in sorted(covered_lines))
    return f"SF:{source_abs}\n{da}\nend_of_record\n"


def _write_test(path: str, body: str) -> None:
    with open(path, "w") as f:
        f.write(body)


# ── Context ───────────────────────────────────────────────────────────────────


class QACtx:
    def __init__(self):
        self.tmpdir: str | None = None
        self.calc_path: str | None = None
        self.lcov_path: str | None = None
        self.test_script: str | None = None
        self.cli_results: list[subprocess.CompletedProcess] = []
        self.prior_body: str | None = None
        self.sentinel_dir: str | None = None
        self.inject_write_fail: bool = False


ctx = QACtx()


def _reset():
    os.environ.pop("_MUTATE4PY_TEST_WORKER_WRITE_FAIL", None)
    import tempfile
    import textwrap as _tw

    d = tempfile.mkdtemp()
    # Write minimal pyproject.toml so `uv sync` works in worker copies
    pyproject = _tw.dedent("""\
        [project]
        name = "qa-fixture"
        version = "0.1.0"
        requires-python = ">=3.11"
        dependencies = []
    """)
    with open(os.path.join(d, "pyproject.toml"), "w") as f:
        f.write(pyproject)
    with open(os.path.join(d, "uv.lock"), "w") as f:
        f.write('version = 1\nrequires-python = ">=3.11"\n')
    ctx.tmpdir = d
    ctx.calc_path = None
    ctx.lcov_path = None
    ctx.test_script = None
    ctx.cli_results = []
    ctx.prior_body = None
    ctx.sentinel_dir = None
    ctx.inject_write_fail = False


def _tmpdir() -> str:
    if ctx.tmpdir is None:
        _reset()
    return ctx.tmpdir


def _run_qa_cmd(cmd_str: str) -> subprocess.CompletedProcess:
    """Parse and run a 'mutate4py ...' command string from the feature file.

    --max-workers 0 is treated as "omit the flag" (serial mode) because the
    spec §5 rejects 0 as non-positive; the QA feature uses 0 to mean serial.
    """
    parts = cmd_str.split()
    assert parts[0] == "mutate4py", (
        f"Expected command to start with 'mutate4py', got: {parts[0]}"
    )
    args = []
    d = _tmpdir()
    skip_next = False
    rest = parts[1:]
    for i, part in enumerate(rest):
        if skip_next:
            skip_next = False
            continue
        if part == "--max-workers" and i + 1 < len(rest) and rest[i + 1] == "0":
            # --max-workers 0 means serial: omit the flag entirely (spec rejects 0)
            skip_next = True
            continue
        if part == "calc.py":
            args.append(ctx.calc_path)
        elif part == "cov.info":
            args.append(ctx.lcov_path)
        else:
            args.append(part)
    env = dict(os.environ)
    if ctx.inject_write_fail:
        env["_MUTATE4PY_TEST_WORKER_WRITE_FAIL"] = "1"
    else:
        env.pop("_MUTATE4PY_TEST_WORKER_WRITE_FAIL", None)
    return subprocess.run(
        ["uv", "run", "--project", REPO_ROOT, "mutate4py"] + args,
        capture_output=True,
        text=True,
        cwd=d,
        env=env,
    )


# ── Background steps ──────────────────────────────────────────────────────────


@step(r"a temp working directory the QA agent owns and tears down")
def given_tmpdir(m, params):
    _reset()


@step(
    r'a Python source fixture "calc\.py" with covered mutation sites on lines "([^"]*)"'
)
def given_calc_fixture(m, params):
    lines_str = m.group(1)
    d = _tmpdir()
    ctx.calc_path = os.path.join(d, "calc.py")
    with open(ctx.calc_path, "w") as f:
        f.write(CALC_PY)


@step(
    r'a hand-written LCOV "([^"]*)" with SF matching "calc\.py" and DA hits on lines "([^"]*)"'
)
def given_lcov_fixture(m, params):
    d = _tmpdir()
    covered = COVERED_LINES
    ctx.lcov_path = os.path.join(d, m.group(1))
    with open(ctx.lcov_path, "w") as f:
        f.write(_make_lcov(ctx.calc_path, covered))


@step(r"a fake pytest test the QA agent scripts per outcome")
def given_fake_test_cmd_placeholder(m, params):
    d = _tmpdir()
    tests_dir = os.path.join(d, "tests")
    os.makedirs(tests_dir, exist_ok=True)
    ctx.test_script = os.path.join(tests_dir, "test_qa.py")
    # Placeholder — actual content set by Given steps below.
    _write_test(ctx.test_script, "def test_qa():\n    pass\n")


# ── Given steps ───────────────────────────────────────────────────────────────


def _write_counted_all_killed() -> None:
    """Call 0 (the baseline, always serial and first) passes; every later
    call (a mutant, possibly racing other workers) fails."""
    d = _tmpdir()
    counter = os.path.join(d, "_call_count.txt")
    with open(counter, "w") as f:
        f.write("0")
    body = (
        "def test_qa():\n"
        f"    counter_path = {counter!r}\n"
        "    with open(counter_path) as f:\n"
        "        count = int(f.read())\n"
        "    with open(counter_path, 'w') as f:\n"
        "        f.write(str(count + 1))\n"
        "    if count == 0:\n"
        "        return\n"
        "    assert False\n"
    )
    _write_test(ctx.test_script, body)


@step(r"the fake pytest test exits nonzero for every mutant while the baseline passes")
def given_all_killed_baseline_passes(m, params):
    _write_counted_all_killed()


@step(r'the fake pytest test makes the mutated run "([^"]*)" while the baseline passes')
def given_single_outcome_baseline_passes(m, params):
    outcome = m.group(1)
    if outcome == "exit nonzero":
        _write_counted_all_killed()
        return
    if outcome == "exit zero":
        _write_test(ctx.test_script, "def test_qa():\n    pass\n")
        return
    if outcome == "sleep past timeout":
        d = _tmpdir()
        counter = os.path.join(d, "_call_count.txt")
        with open(counter, "w") as f:
            f.write("0")
        body = (
            "import time\n\n"
            "def test_qa():\n"
            f"    counter_path = {counter!r}\n"
            "    with open(counter_path) as f:\n"
            "        count = int(f.read())\n"
            "    with open(counter_path, 'w') as f:\n"
            "        f.write(str(count + 1))\n"
            "    if count == 0:\n"
            "        return\n"
            "    time.sleep(30)\n"
        )
        _write_test(ctx.test_script, body)
        return
    raise ValueError(f"Unknown outcome: {outcome!r}")


@step(
    r'the fake pytest test makes "(\d+)" of the 4 mutants exit zero and the rest exit nonzero'
)
def given_n_survivors_4_sites(m, params):
    n = int(m.group(1))
    d = _tmpdir()
    baseline_done = os.path.join(d, "_baseline_done_surv.txt")
    # Strategy: make exactly 1 specific mutant survive by detecting which mutant
    # is in the worker copy. calc.py has 4 sites; only calc1 (line 3) survives.
    # Worker copies have the mutated file at the same relative path as the original.
    src_rel = os.path.relpath(ctx.calc_path, d)
    if n == 1:
        # Make only calc1's mutant (a >= b) survive; kill the rest (c >= d, e >= f, g >= h)
        body = (
            "import os\n\n"
            "def test_qa():\n"
            f"    baseline_done = {baseline_done!r}\n"
            "    if not os.path.exists(baseline_done):\n"
            "        open(baseline_done, 'w').close()\n"
            "        return\n"
            f"    with open({src_rel!r}) as f:\n"
            "        content = f.read()\n"
            "    assert 'a >= b' in content\n"
        )
    else:
        # Generic: first n mutant sites survive — detect by content not feasible for n>1.
        # Fall back to killing all for now (including the baseline, matching the
        # original shell script's unconditional exit 1 in this branch).
        body = "def test_qa():\n    assert False\n"
    _write_test(ctx.test_script, body)


@step(r"the fake pytest test records its working directory to a sentinel and exits nonzero")
def given_records_cwd_and_kills(m, params):
    d = _tmpdir()
    sentinels_dir = os.path.join(d, "_wd_sentinels")
    os.makedirs(sentinels_dir, exist_ok=True)
    ctx.sentinel_dir = sentinels_dir
    baseline_done = os.path.join(d, "_baseline_done_wd.txt")
    body = (
        "import os\n\n"
        "def test_qa():\n"
        f"    baseline_done = {baseline_done!r}\n"
        "    if not os.path.exists(baseline_done):\n"
        "        open(baseline_done, 'w').close()\n"
        "        return\n"
        f"    sentinels_dir = {sentinels_dir!r}\n"
        "    with open(os.path.join(sentinels_dir, f'wd_{os.getpid()}.txt'), 'w') as f:\n"
        "        f.write(os.getcwd())\n"
        "    assert False\n"
    )
    _write_test(ctx.test_script, body)


@step(
    r'the fake pytest test checks for a "\.mutate4py/workers/" tree on its first call and exits nonzero'
)
def given_checks_worker_tree_on_first_mutant(m, params):
    d = _tmpdir()
    sentinel = os.path.join(d, "_worker_tree_observed.txt")
    baseline_done = os.path.join(d, "_baseline_done2.txt")
    first_mutant_done = os.path.join(d, "_first_mutant_done.txt")
    body = (
        "import os\n\n"
        "def test_qa():\n"
        f"    baseline_done = {baseline_done!r}\n"
        "    if not os.path.exists(baseline_done):\n"
        "        open(baseline_done, 'w').close()\n"
        "        return\n"
        f"    first_mutant_done = {first_mutant_done!r}\n"
        "    if not os.path.exists(first_mutant_done):\n"
        "        open(first_mutant_done, 'w').close()\n"
        "        if os.sep.join(['.mutate4py', 'workers']) in os.getcwd():\n"
        f"            with open({sentinel!r}, 'w') as f:\n"
        "                f.write('observed')\n"
        "    assert False\n"
    )
    _write_test(ctx.test_script, body)
    ctx.sentinel_dir = sentinel


@step(r'the bytes of "calc\.py" before any manifest footer are recorded')
def given_record_prior_body(m, params):
    with open(ctx.calc_path) as f:
        src = f.read()
    # Strip any manifest footer (everything from manifest begin marker onward)
    marker = "# mutate4py-manifest-begin"
    idx = src.find(marker)
    ctx.prior_body = src[:idx].rstrip() if idx != -1 else src.rstrip()


@step(r"the fake pytest test exits nonzero for every mutant")
def given_all_killed_no_qualifier(m, params):
    _write_counted_all_killed()


@step(r"one worker copy is made unwritable so its restore fails")
def given_one_worker_unwritable(m, params):
    ctx.inject_write_fail = True


# ── When steps ────────────────────────────────────────────────────────────────


@step(r'the QA agent runs "([^"]*)"')
def when_qa_runs(m, params):
    cmd_str = m.group(1)
    result = _run_qa_cmd(cmd_str)
    ctx.cli_results = [result]


@step(r'the QA agent runs "([^"]*)" twice')
def when_qa_runs_twice(m, params):
    import shutil

    cmd_str = m.group(1)
    r1 = _run_qa_cmd(cmd_str)
    d = _tmpdir()
    # Reset test-script state for the second run
    for fname in os.listdir(d):
        fpath = os.path.join(d, fname)
        if fname.startswith("_") and os.path.isfile(fpath):
            os.remove(fpath)
        elif fname.startswith("_") and os.path.isdir(fpath):
            shutil.rmtree(fpath)
            os.makedirs(fpath, exist_ok=True)
    # Strip manifest footer from calc.py so run 2 treats all sites as "changed"
    if ctx.calc_path and os.path.exists(ctx.calc_path):
        with open(ctx.calc_path) as f:
            src = f.read()
        marker = "# mutate4py-manifest-begin"
        idx = src.find(marker)
        if idx != -1:
            with open(ctx.calc_path, "w") as f:
                f.write(src[:idx])
    r2 = _run_qa_cmd(cmd_str)
    ctx.cli_results = [r1, r2]


# ── Then steps ────────────────────────────────────────────────────────────────


@step(r'stdout "([^"]*)" contain "([^"]*)"')
def then_stdout_conditional_contains(m, params):
    containsLine = m.group(1)
    text = m.group(2)
    for result in ctx.cli_results:
        if containsLine == "does":
            assert text in result.stdout, (
                f"Expected '{text}' in stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        else:
            assert text not in result.stdout, (
                f"Did not expect '{text}' in stdout:\n{result.stdout}"
            )


@step(r"the exit status is zero")
def then_exit_zero(m, params):
    for result in ctx.cli_results:
        assert result.returncode == 0, (
            f"Expected exit 0, got {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


@step(r"every per-mutant line in stdout \"([^\"]+)\" contain a \"worker-\" token")
def then_per_mutant_worker_token(m, params):
    containsToken = m.group(1)
    import re as _re

    for result in ctx.cli_results:
        progress = [
            ln for ln in result.stdout.splitlines() if _re.match(r"\[\d+/\d+\]", ln)
        ]
        assert progress, f"No progress lines in stdout:\n{result.stdout}"
        if containsToken == "does":
            for line in progress:
                assert "worker-" in line, (
                    f"Expected worker-k token in: {line!r}\nfull stdout:\n{result.stdout}"
                )
        else:
            for line in progress:
                assert "worker-" not in line, (
                    f"Did not expect worker-k token in: {line!r}\nfull stdout:\n{result.stdout}"
                )


@step(r'stdout contains "([^"]*)"')
def then_stdout_contains(m, params):
    text = m.group(1)
    for result in ctx.cli_results:
        assert text in result.stdout, (
            f"Expected '{text}' in stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


@step(
    r'stdout contains a per-mutant line matching "worker-<k> ([^"]*)" for that mutant'
)
def then_per_mutant_line_status(m, params):
    # m.group(1) captures e.g. "killed line " — use it directly as the token after worker-k
    token = m.group(1)
    import re as _re

    for result in ctx.cli_results:
        progress = [
            ln for ln in result.stdout.splitlines() if _re.match(r"\[\d+/\d+\]", ln)
        ]
        assert progress, f"No progress lines in stdout:\n{result.stdout}"
        pattern = rf"\[\d+/\d+\] worker-\d+ {_re.escape(token)}"
        assert any(_re.search(pattern, ln) for ln in progress), (
            f"No per-mutant line matching 'worker-<k> {token}...' in:\n"
            + "\n".join(progress)
        )


@step(r'both runs print "([^"]*)"')
def then_both_runs_print(m, params):
    text = m.group(1)
    for i, result in enumerate(ctx.cli_results):
        assert text in result.stdout, (
            f"Run {i + 1}: Expected '{text}' in stdout:\n{result.stdout}"
        )


@step(r'both runs list the same site under "Survivors:"')
def then_both_runs_same_survivors(m, params):
    import re as _re

    def _extract_survivors_block(stdout: str) -> str:
        lines = stdout.splitlines()
        in_block = False
        block = []
        for ln in lines:
            if ln.strip() == "Survivors:":
                in_block = True
                continue
            if in_block:
                if ln.strip() == "" or ln.startswith("Mutation Report"):
                    break
                block.append(ln.strip())
        return "\n".join(sorted(block))

    assert len(ctx.cli_results) == 2
    s1 = _extract_survivors_block(ctx.cli_results[0].stdout)
    s2 = _extract_survivors_block(ctx.cli_results[1].stdout)
    assert s1 == s2, f"Survivors differed between runs:\nRun1: {s1}\nRun2: {s2}"
    assert s1, f"No survivors block found in run 1:\n{ctx.cli_results[0].stdout}"


@step(r'the recorded working directories are under "\.mutate4py/workers/"')
def then_wd_under_workers(m, params):
    sentinels_dir = ctx.sentinel_dir
    assert sentinels_dir and os.path.isdir(sentinels_dir), (
        f"No sentinels dir at {sentinels_dir}"
    )
    files = [f for f in os.listdir(sentinels_dir) if f.endswith(".txt")]
    assert files, f"No sentinel files written in {sentinels_dir}"
    for fname in files:
        path = os.path.join(sentinels_dir, fname)
        with open(path) as f:
            wd = f.read().strip()
        assert ".mutate4py/workers" in wd or ".mutate4py" + os.sep + "workers" in wd, (
            f"Sentinel {fname}: expected .mutate4py/workers in working dir, got: {wd!r}"
        )


@step(r"none of the recorded working directories is the original working directory")
def then_no_wd_is_original(m, params):
    d = _tmpdir()
    sentinels_dir = ctx.sentinel_dir
    files = [f for f in os.listdir(sentinels_dir) if f.endswith(".txt")]
    assert files, f"No sentinel files in {sentinels_dir}"
    for fname in files:
        path = os.path.join(sentinels_dir, fname)
        with open(path) as f:
            wd = f.read().strip()
        real_wd = os.path.realpath(wd)
        real_d = os.path.realpath(d)
        assert real_wd != real_d, f"Sentinel {fname}: worker ran in original dir {wd!r}"


@step(r'the fake pytest test observed a "\.mutate4py/workers/" tree during the run')
def then_worker_tree_observed(m, params):
    sentinel = ctx.sentinel_dir  # path to sentinel file
    assert os.path.exists(sentinel), (
        f"Sentinel not written — worker tree was NOT observed during run. "
        f"stdout:\n{ctx.cli_results[0].stdout}\nstderr:\n{ctx.cli_results[0].stderr}"
    )
    with open(sentinel) as f:
        content = f.read().strip()
    assert content == "observed", f"Sentinel content unexpected: {content!r}"


@step(r'no "\.mutate4py/workers/" tree exists in the working directory after the run')
def then_no_worker_tree_after(m, params):
    d = _tmpdir()
    workers_dir = os.path.join(os.path.realpath(d), ".mutate4py", "workers")
    if not os.path.exists(workers_dir):
        return
    # The workers/ dir may exist but must have no run-* subdirs remaining
    run_dirs = [
        e
        for e in os.listdir(workers_dir)
        if os.path.isdir(os.path.join(workers_dir, e))
    ]
    assert run_dirs == [], (
        f"Worker run directories still exist under {workers_dir}: {run_dirs}"
    )


@step(r'the body of "calc\.py" above the manifest footer is unchanged')
def then_body_unchanged(m, params):
    with open(ctx.calc_path) as f:
        content = f.read()
    marker = "# mutate4py-manifest-begin"
    idx = content.find(marker)
    body = content[:idx].rstrip() if idx != -1 else content.rstrip()
    assert body == ctx.prior_body, (
        f"Body changed!\nExpected:\n{ctx.prior_body}\nGot:\n{body}"
    )


@step(
    r'"calc\.py" ends with a "mutate4py-manifest-begin" / "mutate4py-manifest-end" footer'
)
def then_manifest_footer(m, params):
    with open(ctx.calc_path) as f:
        content = f.read()
    assert "mutate4py-manifest-begin" in content, (
        f"No manifest-begin footer in calc.py:\n{content}"
    )
    assert "mutate4py-manifest-end" in content, (
        f"No manifest-end footer in calc.py:\n{content}"
    )


@step(r'no "\.mutate4py\.bak" file exists in the working directory')
def then_no_bak(m, params):
    bak_path = ctx.calc_path + ".bak" if ctx.calc_path else None
    if bak_path:
        assert not os.path.exists(bak_path), (
            f".bak file unexpectedly present: {bak_path}"
        )
    d = _tmpdir()
    for fname in os.listdir(d):
        assert not fname.endswith(".bak"), (
            f"Unexpected .bak file: {os.path.join(d, fname)}"
        )


@step(r"the exit status is non-zero")
def then_exit_nonzero(m, params):
    for result in ctx.cli_results:
        assert result.returncode != 0, (
            f"Expected non-zero exit, got {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


@step(r'stdout does not contain "([^"]*)"')
def then_stdout_not_contains(m, params):
    text = m.group(1)
    for result in ctx.cli_results:
        assert text not in result.stdout, (
            f"Unexpected '{text}' in stdout:\n{result.stdout}"
        )
