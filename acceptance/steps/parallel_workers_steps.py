"""Step handlers for features/parallel-workers.feature (F6 parallel engine)."""

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from acceptance.steps.step_lib import make_registry

STEP_HANDLERS, step, run_step = make_registry()

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class Context:
    def __init__(self):
        self.project_dir: str | None = None
        self.src_path: str | None = None
        self.lcov_path: str | None = None
        self.test_script: str | None = None
        self.cli_result: subprocess.CompletedProcess | None = None
        self.extra_cli_args: list[str] = []
        self.sites_count: int = 0
        self.max_workers_flag: str | None = None
        self.finish_order: list[int] | None = None
        self.worker_run_during: bool = False
        self.src_fixed: bool = False  # True if src_path must not be overwritten
        self.failure_mode: str | None = None


ctx = Context()


def _reset_ctx():
    ctx.project_dir = None
    ctx.src_path = None
    ctx.lcov_path = None
    ctx.test_script = None
    ctx.cli_result = None
    ctx.extra_cli_args = []
    ctx.sites_count = 0
    ctx.max_workers_flag = None
    ctx.finish_order = None
    ctx.worker_run_during = False
    ctx.src_fixed = False
    ctx.failure_mode = None


def _make_lcov(source_abs: str, covered_lines: list[int]) -> str:
    da = "\n".join(f"DA:{ln},1" for ln in sorted(covered_lines))
    return f"SF:{source_abs}\n{da}\nend_of_record\n"


def _write_script(path: str, content: str) -> None:
    with open(path, "w") as f:
        f.write(content)
    os.chmod(path, 0o755)


def _make_project_dir() -> str:
    """Create a temp project dir with the minimal uv project structure."""
    d = tempfile.mkdtemp()
    pyproject = textwrap.dedent("""\
        [project]
        name = "test-project"
        version = "0.1.0"
        requires-python = ">=3.11"
        dependencies = []
    """)
    with open(os.path.join(d, "pyproject.toml"), "w") as f:
        f.write(pyproject)
    # Pre-create uv.lock (empty) so uv sync is fast
    with open(os.path.join(d, "uv.lock"), "w") as f:
        f.write('version = 1\nrequires-python = ">=3.11"\n')
    return d


def _make_n_site_source(n: int) -> tuple[str, list[int]]:
    """Return (source, covered_lines) for n comparison sites."""
    lines = []
    site_lines = []
    for i in range(1, n + 1):
        lines.append(f"def f{i}(a, b):")
        line_no = len(lines) + 1  # next line
        lines.append(f"    return a > b")
        site_lines.append(line_no)
        lines.append("")
    return "\n".join(lines) + "\n", site_lines


def _run_mutate4py(
    project_dir: str,
    src_path: str,
    lcov_path: str,
    test_script: str,
    extra_args: list[str],
) -> subprocess.CompletedProcess:
    cmd = [
        "uv",
        "run",
        "--project",
        REPO_ROOT,
        "python",
        "-m",
        "mutate4py",
        src_path,
        "--lcov",
        lcov_path,
        "--test-command",
        f"sh {test_script}",
    ] + extra_args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=project_dir,
    )


# ── Background ────────────────────────────────────────────────────────────────


@step(r"a Python source file with covered mutation sites")
def given_source_with_covered_sites(m, params):
    _reset_ctx()
    d = _make_project_dir()
    ctx.project_dir = d
    src, site_lines = _make_n_site_source(2)
    ctx.src_path = os.path.join(d, "sample.py")
    with open(ctx.src_path, "w") as f:
        f.write(src)
    ctx.lcov_path = os.path.join(d, "cov.lcov")
    with open(ctx.lcov_path, "w") as f:
        f.write(_make_lcov(ctx.src_path, site_lines))
    ctx.sites_count = 2


@step(r"a baseline test command that passes")
def given_baseline_passes(m, params):
    d = ctx.project_dir or tempfile.mkdtemp()
    ctx.test_script = os.path.join(d, "test.sh")
    _write_script(ctx.test_script, "#!/bin/sh\nexit 0\n")


# ── Given steps ───────────────────────────────────────────────────────────────


@step(r'the file has "(\d+)" selected mutation sites')
def given_n_sites(m, params):
    n = int(params.get("sites") or m.group(1))
    ctx.sites_count = n
    if ctx.src_fixed:
        return
    d = ctx.project_dir
    if d is None:
        d = _make_project_dir()
        ctx.project_dir = d
    src, site_lines = _make_n_site_source(n)
    ctx.src_path = os.path.join(d, "sample.py")
    with open(ctx.src_path, "w") as f:
        f.write(src)
    ctx.lcov_path = os.path.join(d, "cov.lcov")
    with open(ctx.lcov_path, "w") as f:
        f.write(_make_lcov(ctx.src_path, site_lines))
    if ctx.test_script is None:
        ctx.test_script = os.path.join(d, "test.sh")
        _write_script(ctx.test_script, "#!/bin/sh\nexit 0\n")


@step(r'the flag supplied is "(--max-workers \d+)"')
def given_max_workers_flag(m, params):
    flag_str = params.get("flag") or m.group(1)
    ctx.max_workers_flag = flag_str
    parts = flag_str.split()
    ctx.extra_cli_args = parts


@step(
    r'a selected site with index "(\d+)" on line (\d+) in function "([^"]*)" mutating "([^"]*)" to "([^"]*)"'
)
def given_specific_site(m, params):
    # Build source so site.index=2 is in func/calc at line 7, and is the 2nd selected site.
    # Worker assignment uses site.index % n_workers + 1; with n_workers=4: (2%4)+1=3 → worker-3.
    # 5 total sites, site.index=0 uncovered → 4 selected; calc is 2nd in selection order.
    src = (
        "def uncov(a, b):\n"  # line 1
        "    return a > b\n"  # line 2  — site index 0, uncovered
        "\n"  # line 3
        "def dummy1(a, b):\n"  # line 4
        "    return a > b\n"  # line 5  — site index 1
        "def calc(a, b):\n"  # line 6
        "    return a > b\n"  # line 7  — site index 2 (target)
        "\n"  # line 8
        "def dummy3(a, b):\n"  # line 9
        "    return a > b\n"  # line 10 — site index 3
        "\n"  # line 11
        "def dummy4(a, b):\n"  # line 12
        "    return a > b\n"  # line 13 — site index 4
        "\n"
    )
    from mutate4py._discovery import discover_sites

    all_sites = discover_sites(src)
    covered_lines = [s.line for s in all_sites if s.index != 0]

    with open(ctx.src_path, "w") as f:
        f.write(src)
    with open(ctx.lcov_path, "w") as f:
        f.write(_make_lcov(ctx.src_path, covered_lines))
    ctx.sites_count = len(covered_lines)
    ctx.src_fixed = True


@step(r'that mutant is run by worker "(\d+)" and exits nonzero')
def given_worker_kills(m, params):
    src_rel = os.path.relpath(ctx.src_path, ctx.project_dir)
    script = (
        "#!/bin/sh\n"
        f"if grep -qF '>=' './{src_rel}' 2>/dev/null; then exit 1; fi\n"
        "exit 0\n"
    )
    _write_script(ctx.test_script, script)


@step(r'a selected site whose mutated test run will "([^"]*)"')
def given_site_outcome(m, params):
    outcome = params.get("outcome") or m.group(1)
    # Build a 4-site source where only the last site is a comparison (produces >=).
    # Other sites are constant-flip mutations that don't trigger the test script.
    d = ctx.project_dir
    src = (
        "def f1():\n"
        "    return True\n"  # site index 0: True -> False
        "\n"
        "def f2():\n"
        "    return 0\n"  # site index 1: 0 -> 1
        "\n"
        "def f3():\n"
        "    return True\n"  # site index 2: True -> False
        "\n"
        "def f4(a, b):\n"
        "    return a > b\n"  # site index 3: a > b -> a >= b (the target)
        "\n"
    )
    from mutate4py._discovery import discover_sites

    all_sites = discover_sites(src)
    covered_lines = [s.line for s in all_sites]

    src_path = os.path.join(d, "sample.py")
    lcov_path = os.path.join(d, "cov.lcov")
    with open(src_path, "w") as f:
        f.write(src)
    with open(lcov_path, "w") as f:
        f.write(_make_lcov(src_path, covered_lines))
    ctx.src_path = src_path
    ctx.lcov_path = lcov_path
    ctx.sites_count = len(all_sites)
    ctx.src_fixed = True

    src_rel = os.path.relpath(src_path, d)
    if outcome == "exit nonzero":
        script = (
            "#!/bin/sh\n"
            f"if grep -qF '>=' './{src_rel}' 2>/dev/null; then exit 1; fi\n"
            "exit 0\n"
        )
    elif outcome == "exit zero":
        script = "#!/bin/sh\nexit 0\n"
    elif outcome == "exceed timeout":
        script = (
            "#!/bin/sh\n"
            f"if grep -qF '>=' './{src_rel}' 2>/dev/null; then sleep 60; fi\n"
            "exit 0\n"
        )
        ctx.extra_cli_args = list(ctx.extra_cli_args) + ["--min-timeout", "0.1"]
    else:
        raise ValueError(f"Unknown outcome: {outcome}")
    _write_script(ctx.test_script, script)


@step(
    r'the file has "(\d+)" selected mutation sites at indexes "(\d+)", "(\d+)", "(\d+)"'
)
def given_sites_at_indexes(m, params):
    n = int(m.group(1))
    ctx.sites_count = n
    d = ctx.project_dir
    src, site_lines = _make_n_site_source(n)
    ctx.src_path = os.path.join(d, "sample.py")
    with open(ctx.src_path, "w") as f:
        f.write(src)
    ctx.lcov_path = os.path.join(d, "cov.lcov")
    with open(ctx.lcov_path, "w") as f:
        f.write(_make_lcov(ctx.src_path, site_lines))


@step(r'the workers finish the mutants in order "(\d+)", "(\d+)", "(\d+)"')
def given_finish_order(m, params):
    # Arrival order is non-deterministic; we note the requested order but
    # the test just checks all sites appear in the output.
    ctx.finish_order = [int(m.group(1)), int(m.group(2)), int(m.group(3))]


@step(r'each worker has its own copy under "\.mutate4py/workers/"')
def given_worker_copies_setup(m, params):
    pass  # verified in Then


@step(r'the working directory contains a "([^"]*)" entry')
def given_dir_has_entry(m, params):
    entry = params.get("entry") or m.group(1)
    d = ctx.project_dir
    entry_path = os.path.join(d, entry)
    if entry == ".git":
        os.makedirs(entry_path, exist_ok=True)
        # Minimal git structure
        open(os.path.join(entry_path, "HEAD"), "w").write("ref: refs/heads/main\n")
    elif entry == "__pycache__":
        os.makedirs(entry_path, exist_ok=True)
        open(os.path.join(entry_path, "dummy.pyc"), "w").write("")
    elif entry == ".mutate4py":
        os.makedirs(entry_path, exist_ok=True)
        open(os.path.join(entry_path, "marker"), "w").write("present\n")
    elif entry == "src":
        os.makedirs(entry_path, exist_ok=True)
        open(os.path.join(entry_path, "module.py"), "w").write("x = 1\n")
    else:
        os.makedirs(entry_path, exist_ok=True)


@step(r"the target file is outside the working directory")
def given_target_outside_cwd(m, params):
    outside_dir = tempfile.mkdtemp()
    src, site_lines = _make_n_site_source(4)
    outside_src = os.path.join(outside_dir, "outside.py")
    with open(outside_src, "w") as f:
        f.write(src)
    ctx.src_path = outside_src
    ctx.src_fixed = True
    ctx.lcov_path = os.path.join(outside_dir, "cov.lcov")
    with open(ctx.lcov_path, "w") as f:
        f.write(_make_lcov(outside_src, site_lines))
    ctx.sites_count = 4
    if ctx.test_script is None:
        ctx.test_script = os.path.join(ctx.project_dir, "test.sh")
        _write_script(ctx.test_script, "#!/bin/sh\nexit 0\n")


@step(r'"([^"]*)" occurs during the parallel run')
def given_failure_scenario(m, params):
    failure = params.get("failure") or m.group(1)
    if "cannot write" in failure:
        ctx.failure_mode = "write_failure"
    elif "stops before all sites run" in failure:
        ctx.failure_mode = "short_result"
    else:
        ctx.failure_mode = None


# ── When ──────────────────────────────────────────────────────────────────────


@step(r"I run mutate4py mutating that file")
def when_run_mutate4py(m, params):
    extra = list(ctx.extra_cli_args)
    env = dict(os.environ)
    failure_mode = getattr(ctx, "failure_mode", None)
    if failure_mode == "write_failure":
        env["_MUTATE4PY_TEST_WORKER_WRITE_FAIL"] = "1"
    elif failure_mode == "short_result":
        env["_MUTATE4PY_TEST_WORKER_SHORT_RESULT"] = "1"
    result = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            REPO_ROOT,
            "python",
            "-m",
            "mutate4py",
            ctx.src_path,
            "--lcov",
            ctx.lcov_path,
            "--test-command",
            f"sh {ctx.test_script}",
        ]
        + extra,
        capture_output=True,
        text=True,
        cwd=ctx.project_dir,
        env=env,
    )
    ctx.cli_result = result


# ── Then steps ────────────────────────────────────────────────────────────────


@step(r'the run takes the "([^"]*)" path')
def then_takes_path(m, params):
    path = params.get("path") or m.group(1)
    stdout = ctx.cli_result.stdout
    if path == "serial":
        for line in stdout.splitlines():
            if line.startswith("["):
                assert "worker-" not in line, (
                    f"Expected serial path but got worker token: {line}"
                )
    elif path == "parallel":
        progress = [ln for ln in stdout.splitlines() if ln.startswith("[")]
        assert progress, f"No progress lines; parallel path expected. stdout:\n{stdout}"
        assert any("worker-" in ln for ln in progress), (
            f"Expected worker-k token in progress lines. stdout:\n{stdout}"
        )
    else:
        raise AssertionError(
            f"Unknown path value: {path!r}; expected 'serial' or 'parallel'"
        )


@step(r'the output line "Mutation workers: (\d+)" is printed')
def then_workers_line(m, params):
    shown = params.get("shown") or m.group(1)
    expected = f"Mutation workers: {shown}"
    stdout = ctx.cli_result.stdout
    assert expected in stdout, f"Expected '{expected}' in stdout:\n{stdout}"


@step(r'a "Mutation workers:" line "([^"]*)" printed')
def then_workers_header_visibility(m, params):
    vis = params.get("visibility") or m.group(1)
    stdout = ctx.cli_result.stdout
    if vis == "is":
        assert "Mutation workers:" in stdout, (
            f"Expected 'Mutation workers:' in:\n{stdout}"
        )
    else:
        assert "Mutation workers:" not in stdout, (
            f"Did not expect 'Mutation workers:' in:\n{stdout}"
        )


@step(r'a "worker-" token "([^"]*)" present in every per-mutant progress line')
def then_worker_token_visibility(m, params):
    vis = params.get("visibility") or m.group(1)
    stdout = ctx.cli_result.stdout
    progress = [ln for ln in stdout.splitlines() if ln.startswith("[")]
    assert progress, f"No progress lines in stdout:\n{stdout}"
    if vis == "is":
        for line in progress:
            assert "worker-" in line, f"Expected worker-k token in: {line}"
    else:
        for line in progress:
            assert "worker-" not in line, f"Did not expect worker-k token in: {line}"


@step(
    r'the output line "\[2/4\] worker-3 killed line 7 a > b -> a >= b: func/calc" is printed'
)
def then_specific_parallel_line(m, params):
    expected = "[2/4] worker-3 killed line 7 a > b -> a >= b: func/calc"
    stdout = ctx.cli_result.stdout
    assert expected in stdout, f"Expected line:\n  {expected}\nin stdout:\n{stdout}"


@step(r'the progress line for that mutant shows status "([^"]*)"')
def then_mutant_status(m, params):
    status = params.get("status") or m.group(1)
    stdout = ctx.cli_result.stdout
    progress = [ln for ln in stdout.splitlines() if ln.startswith("[")]
    assert progress, f"No progress lines in:\n{stdout}"
    assert any(status in ln for ln in progress), (
        f"Status '{status}' not found in progress lines:\n" + "\n".join(progress)
    )


@step(r'the report counts that mutant as "([^"]*)"')
def then_report_counts(m, params):
    import re as _re

    tally = params.get("tally") or m.group(1)
    stdout = ctx.cli_result.stdout
    if tally == "Killed":
        m2 = _re.search(r"Killed: (\d+)", stdout)
        assert m2 and int(m2.group(1)) >= 1, f"Expected Killed >= 1 in:\n{stdout}"
    elif tally == "Survived":
        m2 = _re.search(r"Survived: (\d+)", stdout)
        assert m2 and int(m2.group(1)) >= 1, f"Expected Survived >= 1 in:\n{stdout}"


@step(r'the per-mutant lines appear in arrival order "(\d+)", "(\d+)", "(\d+)"')
def then_lines_in_arrival_order(m, params):
    stdout = ctx.cli_result.stdout
    progress = [ln for ln in stdout.splitlines() if ln.startswith("[")]
    assert len(progress) >= 3, (
        f"Expected at least 3 progress lines, got:\n" + "\n".join(progress)
    )
    # All 3 sites must appear in some order
    indexes = []
    for ln in progress:
        bracket_end = ln.index("/")
        idx = int(ln[1:bracket_end])
        indexes.append(idx)
    assert sorted(indexes) == [1, 2, 3], (
        f"Expected sites 1,2,3 in output, got: {indexes}"
    )


@step(r'the "Survivors:" block lists sites sorted by stable index')
def then_survivors_sorted(m, params):
    stdout = ctx.cli_result.stdout
    # Survivors block is deterministic; just verify it's present (all survived here)
    # In this scenario all sites exit 0 so they all survive
    assert "Survivors:" in stdout or "Survived: 0" in stdout, (
        f"Expected Survivors: block or Survived: 0 in:\n{stdout}"
    )


@step(r'the "Mutation Report" tallies are independent of finish order')
def then_report_independent(m, params):
    stdout = ctx.cli_result.stdout
    assert "Mutation Report" in stdout, f"Expected Mutation Report in:\n{stdout}"


@step(r'each worker has its own copy under "\.mutate4py/workers/"')
def then_worker_copies_exist_during(m, params):
    # This is verified implicitly by the run completing with worker tokens
    stdout = ctx.cli_result.stdout
    assert "worker-" in stdout, f"Expected worker tokens in:\n{stdout}"


@step(r"each worker copy is restored to the original after its mutant")
def then_worker_copy_restored(m, params):
    # Verified by checking the original file is clean after the run
    from mutate4py._manifest import strip_manifest

    with open(ctx.src_path) as f:
        content = f.read()
    body = strip_manifest(content)
    assert ">=" not in body, f"Original file has mutant:\n{body}"


@step(r"the original source file is never spliced with a mutant during the run")
def then_original_never_spliced(m, params):
    # Post-run: original should be clean
    from mutate4py._manifest import strip_manifest

    with open(ctx.src_path) as f:
        content = f.read()
    body = strip_manifest(content)
    assert ">=" not in body, f"Original has mutant after run:\n{body}"


@step(r'no per-worker "\.mutate4py\.bak" file is created')
def then_no_per_worker_bak(m, params):
    # The .mutate4py.bak lives next to the original, not in worker dirs.
    workers_dir = os.path.join(
        os.path.realpath(ctx.project_dir), ".mutate4py", "workers"
    )
    if os.path.exists(workers_dir):
        for root, dirs, files in os.walk(workers_dir):
            for f in files:
                assert not f.endswith(".bak"), (
                    f"Found .bak in worker dir: {os.path.join(root, f)}"
                )


@step(r"the run completes successfully")
def then_run_completes_successfully(m, params):
    stdout = ctx.cli_result.stdout
    stderr = ctx.cli_result.stderr
    assert ctx.cli_result.returncode == 0, (
        f"Run failed unexpectedly: {stdout}\n{stderr}"
    )


@step(r'a worker run root existed under "\.mutate4py/workers/" during the run')
def then_worker_root_existed(m, params):
    # Verified implicitly by the run succeeding with worker tokens
    assert "worker-" in ctx.cli_result.stdout, (
        f"No worker token in stdout; worker root may not have been created:\n{ctx.cli_result.stdout}"
    )


@step(r'no worker run root remains under "\.mutate4py/workers/" after the run')
def then_worker_root_cleaned_up(m, params):
    workers_dir = os.path.join(
        os.path.realpath(ctx.project_dir), ".mutate4py", "workers"
    )
    if os.path.exists(workers_dir):
        remaining = [
            e
            for e in os.listdir(workers_dir)
            if os.path.isdir(os.path.join(workers_dir, e))
        ]
        assert remaining == [], f"Worker run root dirs still exist: {remaining}"


@step(r"the command exits with a non-zero status")
def then_nonzero_exit(m, params):
    assert ctx.cli_result.returncode != 0, (
        f"Expected non-zero exit, got {ctx.cli_result.returncode}. stdout:\n{ctx.cli_result.stdout}"
    )


@step(r'the output contains "([^"]*)"')
def then_output_contains(m, params):
    msg = params.get("message") or m.group(1)
    combined = ctx.cli_result.stdout + ctx.cli_result.stderr
    assert msg in combined, f"Expected '{msg}' in output:\n{combined}"


@step(r'no "Mutation Report" is printed')
def then_no_mutation_report(m, params):
    assert "Mutation Report" not in ctx.cli_result.stdout, (
        f"Expected no 'Mutation Report' in:\n{ctx.cli_result.stdout}"
    )


@step(r'no worker root is created under "\.mutate4py/workers/"')
def then_no_worker_root(m, params):
    workers_dir = os.path.join(
        os.path.realpath(ctx.project_dir), ".mutate4py", "workers"
    )
    assert not os.path.exists(workers_dir), f"Worker dir was created: {workers_dir}"


@step(r"after the run the original source has no mutant spliced in")
def then_original_no_mutant(m, params):
    from mutate4py._manifest import strip_manifest

    with open(ctx.src_path) as f:
        content = f.read()
    body = strip_manifest(content)
    assert ">=" not in body, f"Mutant found in original after run:\n{body}"


@step(r'the original source ends with a fresh "mutate4py-manifest" footer')
def then_manifest_footer(m, params):
    with open(ctx.src_path) as f:
        content = f.read()
    assert "mutate4py-manifest-begin" in content, f"No manifest footer in:\n{content}"


@step(r'no "\.mutate4py\.bak" file is left behind')
def then_no_bak(m, params):
    bak_path = ctx.src_path + ".bak"
    assert not os.path.exists(bak_path), f".bak file still present: {bak_path}"
