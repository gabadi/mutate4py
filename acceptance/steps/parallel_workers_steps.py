"""Step handlers for features/parallel-workers.feature (F6 parallel engine)."""

import os
import subprocess
import sys
import tempfile
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from acceptance.steps.cli_surface_helpers import survivor_flag
from acceptance.steps.parallel_workers_helpers import (
    assert_measured_in_original,
    assert_mutants_ran_in_workers,
    assert_original_never_spliced,
    assert_worker_tree_seen_during_run,
    placement_probe,
    read_placements,
    report_tally,
    survivor_lines,
)
from acceptance.steps.run_loop_helpers import (
    ROOT_CONFTEST,
    SAMPLE_MODULE,
    compare_source,
    function_names,
    outcome_test_body,
)
from acceptance.steps.nested_pytest_helpers import nested_pytest_env
from acceptance.steps.step_lib import make_registry
from mutate4py._manifest import strip_manifest

STEP_HANDLERS, step, run_step = make_registry()

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class Context:
    def __init__(self):
        self.project_dir: str | None = None
        self.src_path: str | None = None
        self.test_script: str | None = None
        self.cli_result: subprocess.CompletedProcess | None = None
        self.extra_cli_args: list[str] = []
        self.sites_count: int = 0
        self.max_workers_flag: str | None = None
        self.worker_run_during: bool = False
        self.src_fixed: bool = False  # True if src_path must not be overwritten
        self.failure_mode: str | None = None
        # The functions the project's tests call, and each one's outcome under its Mutant.
        self.outcomes: dict[str, str] = {}
        self.placement_record: str | None = None
        # The source body above the manifest footer before the run, and the runs' results.
        self.expected_body: str | None = None
        self.runs: list[subprocess.CompletedProcess] = []
        # Set for src-layout scenarios: the orchestrator's interpreter must see the
        # original src as an installed package (ADR 0015), so it is put on PYTHONPATH.
        self.orchestrator_pythonpath: str | None = None
        # Set for the project-venv src-layout scenario: the orchestrator runs under the
        # project's own .venv, where the original src is an editable install (ADR 0015).
        self.orchestrator_python: str | None = None
        # True only for the scenario that keeps pytest plugin autoload on (see _setup_src_layout).
        self.autoload: bool = False


ctx = Context()


def _reset_ctx():
    ctx.project_dir = None
    ctx.src_path = None
    ctx.test_script = None
    ctx.cli_result = None
    ctx.extra_cli_args = []
    ctx.sites_count = 0
    ctx.max_workers_flag = None
    ctx.worker_run_during = False
    ctx.src_fixed = False
    ctx.failure_mode = None
    ctx.outcomes = {}
    ctx.placement_record = None
    ctx.expected_body = None
    ctx.runs = []
    ctx.orchestrator_pythonpath = None
    ctx.orchestrator_python = None
    ctx.autoload = False


def _write_test(path: str, body: str) -> None:
    with open(path, "w") as f:
        f.write(body)


def _tests_dir(d: str) -> str:
    tests_dir = os.path.join(d, "tests")
    os.makedirs(tests_dir, exist_ok=True)
    return tests_dir


def _make_project_dir() -> str:
    """Create a temp project dir with the minimal uv project structure.

    The dev group names pytest-cov because the run's nested pytest loads it explicitly
    (autoload is off, nested_pytest_helpers.py) and mutate4py passes `--no-cov` to a pytest
    that has it: the Worker venvs must have the plugin the orchestrator names."""
    d = tempfile.mkdtemp()
    pyproject = textwrap.dedent("""\
        [project]
        name = "test-project"
        version = "0.1.0"
        requires-python = ">=3.11"
        dependencies = []

        [dependency-groups]
        dev = ["pytest==9.1.1", "pytest-cov==7.1.0"]
    """)
    with open(os.path.join(d, "pyproject.toml"), "w") as f:
        f.write(pyproject)
    # An empty conftest.py puts the project root on sys.path for the tests.
    with open(os.path.join(d, "conftest.py"), "w") as f:
        f.write(ROOT_CONFTEST)
    # No pre-made uv.lock: it would not list pytest, so uv re-resolves the dev group.
    return d


def _write_tests(outcomes: dict[str, str], probe: str = "") -> None:
    """Write the project's tests: one per function, each ending as `outcomes` says under its Mutant."""
    ctx.outcomes = dict(outcomes)
    _write_test(ctx.test_script, outcome_test_body(SAMPLE_MODULE, ctx.outcomes, probe))


def _write_n_site_project(n: int) -> None:
    """A sample module of n comparison functions with tests that reach every one (all Mutants survive)."""
    d = ctx.project_dir
    source, _ = compare_source(n)
    ctx.src_path = os.path.join(d, f"{SAMPLE_MODULE}.py")
    with open(ctx.src_path, "w") as f:
        f.write(source)
    ctx.sites_count = n
    ctx.test_script = os.path.join(_tests_dir(d), "test_qa.py")
    _write_tests({name: "survive" for name in function_names(n)})


# ── Background ────────────────────────────────────────────────────────────────


@step(r"a Python source file with covered mutation sites")
def given_source_with_covered_sites(m, params):
    _reset_ctx()
    ctx.project_dir = _make_project_dir()
    _write_n_site_project(2)


@step(r"a baseline test command that passes")
def given_baseline_passes(m, params):
    # The project's tests (written above) reach every site and pass on the original code.
    assert ctx.test_script is not None, "no project tests were written"


# ── Given steps ───────────────────────────────────────────────────────────────


@step(r'the file has "(\d+)" selected mutation sites')
def given_n_sites(m, params):
    n = int(params.get("sites") or m.group(1))
    ctx.sites_count = n
    if ctx.src_fixed:
        return
    _write_n_site_project(n)


@step(r'the flag supplied is "(--max-workers \d+)"')
def given_max_workers_flag(m, params):
    flag_str = params.get("flag") or m.group(1)
    ctx.max_workers_flag = flag_str
    parts = flag_str.split()
    ctx.extra_cli_args = parts


@step(r'the max-workers flag is "([^"]*)"')
def given_max_workers_flag_or_default(m, params):
    flag_str = params.get("flag") or m.group(1)
    if flag_str == "(unset)":
        ctx.max_workers_flag = None
        ctx.extra_cli_args = []
        return
    ctx.max_workers_flag = flag_str
    ctx.extra_cli_args = flag_str.split()


@step(r'a selected site with index "(\d+)" on line (\d+) in function "([^"]*)" mutating "([^"]*)" to "([^"]*)"')
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
    with open(ctx.src_path, "w") as f:
        f.write(src)
    # The tests call every function but `uncov`, so its site is the one uncovered site.
    _write_tests({name: "survive" for name in ("dummy1", "calc", "dummy3", "dummy4")})
    ctx.sites_count = 4
    ctx.src_fixed = True


@step(r'that mutant is run by worker "(\d+)" and exits nonzero')
def given_worker_kills(m, params):
    _write_tests({**ctx.outcomes, "calc": "kill"})


_OUTCOME_FOR_RUN = {"exit nonzero": "kill", "exit zero": "survive", "exceed timeout": "timeout"}


@step(r'a selected site whose mutated test run will "([^"]*)"')
def given_site_outcome(m, params):
    outcome = params.get("outcome") or m.group(1)
    if outcome not in _OUTCOME_FOR_RUN:
        raise ValueError(f"Unknown outcome: {outcome}")
    # Four sites; only the last one, `a > b`, is the target whose test is scripted.
    src = (
        "def f1(a, b):\n"
        "    return True\n"  # site index 0: True -> False
        "\n"
        "def f2(a, b):\n"
        "    return 0\n"  # site index 1: 0 -> 1
        "\n"
        "def f3(a, b):\n"
        "    return True\n"  # site index 2: True -> False
        "\n"
        "def f4(a, b):\n"
        "    return a > b\n"  # site index 3: a > b -> a >= b (the target)
        "\n"
    )
    ctx.src_path = os.path.join(ctx.project_dir, f"{SAMPLE_MODULE}.py")
    with open(ctx.src_path, "w") as f:
        f.write(src)
    ctx.sites_count = 4
    ctx.src_fixed = True
    _write_tests({"f1": "survive", "f2": "survive", "f3": "survive", "f4": _OUTCOME_FOR_RUN[outcome]})
    if outcome == "exceed timeout":
        ctx.extra_cli_args = list(ctx.extra_cli_args) + ["--min-timeout", "0.1", "--timeout-factor", "1"]


@step(r'"(\d+)" of the mutants survive and the rest are killed')
def given_some_survive(m, params):
    survivors = int(params.get("survivedCount") or m.group(1))
    names = function_names(ctx.sites_count)
    outcomes = ["survive"] * survivors + ["kill"] * (len(names) - survivors)
    _write_tests(dict(zip(names, outcomes)))


@step(r"the tests record where they run")
def given_tests_record_placement(m, params):
    ctx.placement_record = os.path.join(ctx.project_dir, "placements.txt")
    workers_dir = os.path.join(ctx.project_dir, ".mutate4py", "workers")
    probe = placement_probe(ctx.placement_record, workers_dir, ctx.src_path)
    # Every Mutant is killed, so no survivor is re-run and each record is a mutated run.
    _write_tests({name: "kill" for name in ctx.outcomes}, probe)


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
        raise ValueError(
            f"Unknown working-directory entry fixture: {entry!r}; expected one of .git, __pycache__, .mutate4py, src"
        )


@step(r"the target file is outside the working directory")
def given_target_outside_cwd(m, params):
    outside_dir = tempfile.mkdtemp()
    src, _ = compare_source(4)
    outside_src = os.path.join(outside_dir, "outside.py")
    with open(outside_src, "w") as f:
        f.write(src)
    ctx.src_path = outside_src
    ctx.src_fixed = True
    ctx.sites_count = 4
    # The project's tests reach the outside module, so its sites are covered and selected.
    body = outcome_test_body("outside", {name: "survive" for name in function_names(4)})
    reach = f"import sys\n\nsys.path.insert(0, {outside_dir!r})\n\n"
    _write_test(os.path.join(_tests_dir(ctx.project_dir), "test_outside.py"), reach + body)


_SRC_LAYOUT_SOURCE = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"
_SRC_LAYOUT_TEST = (
    "from demo import add, sub\n"
    "\n"
    "\n"
    "def test_add():\n"
    "    assert add(2, 3) == 5\n"
    "\n"
    "\n"
    "def test_sub():\n"
    "    assert sub(5, 3) == 2\n"
)


def _write_src_layout_project(d: str, *, with_cov: bool) -> str:
    """Rewrite the project as a hatchling src-layout package; return the source path."""
    dev = '"pytest==9.1.1", "pytest-cov"' if with_cov else '"pytest==9.1.1"'
    pyproject = textwrap.dedent(f"""\
        [project]
        name = "demo"
        version = "0.1.0"
        requires-python = ">=3.11"
        dependencies = []

        [dependency-groups]
        dev = [{dev}]

        [build-system]
        requires = ["hatchling==1.31.0"]
        build-backend = "hatchling.build"

        [tool.hatch.build.targets.wheel]
        packages = ["src/demo"]
    """)
    with open(os.path.join(d, "pyproject.toml"), "w") as f:
        f.write(pyproject)
    pkg_dir = os.path.join(d, "src", "demo")
    os.makedirs(pkg_dir, exist_ok=True)
    src_path = os.path.join(pkg_dir, "__init__.py")
    with open(src_path, "w") as f:
        f.write(_SRC_LAYOUT_SOURCE)
    _write_test(os.path.join(_tests_dir(d), "test_demo.py"), _SRC_LAYOUT_TEST)
    return src_path


def _setup_src_layout(*, with_cov: bool) -> None:
    d = ctx.project_dir
    if d is None:
        d = _make_project_dir()
        ctx.project_dir = d
    ctx.src_path = _write_src_layout_project(d, with_cov=with_cov)
    ctx.orchestrator_pythonpath = os.path.join(d, "src")
    ctx.sites_count = 2


def _setup_project_venv_src_layout() -> None:
    """Scenario 14 (ADR 0015): the orchestrator runs under the project's own .venv, where the
    original src is an editable install; _run_mutate4py invokes that interpreter."""
    d = ctx.project_dir
    if d is None:
        d = _make_project_dir()
        ctx.project_dir = d
    ctx.src_path = _write_src_layout_project(d, with_cov=True)
    subprocess.run(["uv", "sync"], cwd=d, check=True)
    ctx.orchestrator_python = os.path.join(d, ".venv", "bin", "python")
    ctx.sites_count = 2


@step(r"the project is a src-layout editable package with pytest and pytest-cov")
def given_src_layout_with_cov(m, params):
    _setup_project_venv_src_layout()


@step(r"the project is a src-layout editable package with pytest but without pytest-cov")
def given_src_layout_without_cov(m, params):
    _setup_src_layout(with_cov=False)
    # parallel-workers-15 is the ONE scenario that keeps pytest plugin autoload on (every other
    # acceptance run turns it off, nested_pytest_helpers.py). Its Worker venv has no pytest-cov while
    # the orchestrator has it, which one explicit `-p pytest_cov` cannot express, and autoload is the
    # default path a user's run takes.
    ctx.autoload = True


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


def _run_mutate4py(extra: list[str]) -> subprocess.CompletedProcess:
    env = nested_pytest_env(autoload=ctx.autoload)
    if ctx.orchestrator_python:
        # REPO_ROOT/src lies outside the project, so the Worker rebase leaves it alone.
        env["PYTHONPATH"] = os.path.join(REPO_ROOT, "src")
        cmd = [ctx.orchestrator_python, "-m", "mutate4py"]
    else:
        cmd = ["uv", "run", "--project", REPO_ROOT, "python", "-m", "mutate4py"]
        if ctx.orchestrator_pythonpath:
            env["PYTHONPATH"] = ctx.orchestrator_pythonpath
    failure_mode = getattr(ctx, "failure_mode", None)
    if failure_mode == "write_failure":
        env["_MUTATE4PY_TEST_WORKER_WRITE_FAIL"] = "1"
    elif failure_mode == "short_result":
        env["_MUTATE4PY_TEST_WORKER_SHORT_RESULT"] = "1"
    # Scored run: an unaccepted survivor exits 3. These scenarios test worker
    # behaviour, not the survivor gate, so they allow survivors and assert exit 0.
    args = cmd + [ctx.src_path, "--pytest-args", "tests"] + extra
    args += survivor_flag(args)
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        cwd=ctx.project_dir,
        env=env,
    )


def _record_expected_body() -> None:
    with open(ctx.src_path) as f:
        # A manifest footer always follows exactly one newline, so start from a body that ends in one.
        ctx.expected_body = strip_manifest(f.read()).rstrip("\n") + "\n"
    with open(ctx.src_path, "w") as f:
        f.write(ctx.expected_body)


@step(r"I run mutate4py mutating that file")
def when_run_mutate4py(m, params):
    _record_expected_body()
    ctx.cli_result = _run_mutate4py(list(ctx.extra_cli_args))


@step(r"I run mutate4py mutating that file twice")
def when_run_mutate4py_twice(m, params):
    _record_expected_body()
    ctx.runs = []
    for _ in range(2):
        # The first run embeds a manifest; start each run from the same input.
        with open(ctx.src_path, "w") as f:
            f.write(ctx.expected_body)
        ctx.runs.append(_run_mutate4py(list(ctx.extra_cli_args)))
    ctx.cli_result = ctx.runs[-1]


# ── Then steps ────────────────────────────────────────────────────────────────


@step(r"the same file run without --max-workers reports the same Killed and Survived counts")
def then_serial_counts_match(m, params):
    import re as _re

    serial_args: list[str] = []
    skip_value = False
    for arg in ctx.extra_cli_args:
        if skip_value:
            skip_value = False
        elif arg == "--max-workers":
            skip_value = True
        else:
            serial_args.append(arg)
    # The parallel run embeds a manifest into the source; restore the original text so the
    # serial run mutates the same input rather than selecting 0 unchanged sites.
    with open(ctx.src_path, "w") as f:
        f.write(_SRC_LAYOUT_SOURCE)
    serial = _run_mutate4py(serial_args)
    for tally in ("Killed", "Survived"):
        parallel_m = _re.search(rf"{tally}: (\d+)", ctx.cli_result.stdout)
        serial_m = _re.search(rf"{tally}: (\d+)", serial.stdout)
        assert parallel_m and serial_m, f"Expected {tally} in both runs:\n{ctx.cli_result.stdout}\n{serial.stdout}"
        assert parallel_m.group(1) == serial_m.group(1), (
            f"{tally}: parallel {parallel_m.group(1)} != serial {serial_m.group(1)}"
        )


@step(r'the run takes the "([^"]*)" path')
def then_takes_path(m, params):
    path = params.get("path") or m.group(1)
    stdout = ctx.cli_result.stdout
    progress = [ln for ln in stdout.splitlines() if ln.startswith("[")]
    assert progress, f"No per-mutant progress lines. stdout:\n{stdout}"
    # The worker-<k> token tracks the path: on every per-mutant line when parallel, on none when serial.
    if path == "serial":
        for line in progress:
            assert "worker-" not in line, f"Expected serial path but got worker token: {line}"
    elif path == "parallel":
        for line in progress:
            assert "worker-" in line, f"Expected worker-k token in: {line}"
    else:
        raise AssertionError(f"Unknown path value: {path!r}; expected 'serial' or 'parallel'")


@step(r'the workers header is "([^"]*)"')
def then_workers_header(m, params):
    header = params.get("header") or m.group(1)
    lines = ctx.cli_result.stdout.splitlines()
    shown = [ln for ln in lines if ln.startswith("Mutation workers:")]
    # The line tracks the flag, not the path: it is absent only when --max-workers is unset.
    if header == "(none)":
        assert not shown, f"Did not expect a 'Mutation workers:' line in:\n{ctx.cli_result.stdout}"
    else:
        assert shown == [header], f"Expected the single header line {header!r}, got {shown} in:\n{ctx.cli_result.stdout}"


@step(r'the output line "Total mutation sites: (\d+)" is printed')
def then_total_sites_line(m, params):
    total = params.get("total") or m.group(1)
    expected = f"Total mutation sites: {total}"
    stdout = ctx.cli_result.stdout
    assert expected in stdout, f"Expected '{expected}' in stdout:\n{stdout}"


@step(r'the output line "\[2/4\] worker-3 killed line 7 a > b -> a >= b: func/calc" is printed')
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
    assert any(status in ln for ln in progress), f"Status '{status}' not found in progress lines:\n" + "\n".join(
        progress
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
    else:
        raise AssertionError(f"Unknown tally value: {tally!r}; expected 'Killed' or 'Survived'")


@step(r'both runs print "(Killed|Survived): (\d+)"')
def then_both_runs_print(m, params):
    label = m.group(1)
    expected = int(m.group(2))
    assert len(ctx.runs) == 2, "the file was not run twice"
    for run in ctx.runs:
        assert run.returncode == 0, f"Run failed unexpectedly: {run.stdout}\n{run.stderr}"
        assert report_tally(run.stdout, label) == expected, f"{label} differs from {expected}:\n{run.stdout}"


@step(r'both runs list the same site under "Survivors:"')
def then_both_runs_list_same_survivor(m, params):
    first, second = (survivor_lines(run.stdout) for run in ctx.runs)
    assert first, f"the first run listed no survivor:\n{ctx.runs[0].stdout}"
    assert first == second, f"survivors differ between runs: {first} != {second}"


@step(r"the Measurement ran in the original directory")
def then_measured_in_original(m, params):
    assert_measured_in_original(read_placements(ctx.placement_record), ctx.project_dir, len(ctx.outcomes))


@step(r'every mutated test run ran under a worker copy in "\.mutate4py/workers/"')
def then_mutants_ran_in_worker_copies(m, params):
    assert_mutants_ran_in_workers(read_placements(ctx.placement_record), ctx.project_dir, len(ctx.outcomes))


@step(r"the original source never held a mutant while the tests ran")
def then_original_never_held_a_mutant(m, params):
    assert_original_never_spliced(read_placements(ctx.placement_record))


@step(r'every mutated test run saw a worker tree under "\.mutate4py/workers/"')
def then_mutated_runs_saw_worker_tree(m, params):
    assert_worker_tree_seen_during_run(read_placements(ctx.placement_record), len(ctx.outcomes))


@step(r'no per-worker "\.mutate4py\.bak" file is created')
def then_no_per_worker_bak(m, params):
    # The .mutate4py.bak lives next to the original, not in worker dirs.
    workers_dir = os.path.join(os.path.realpath(ctx.project_dir), ".mutate4py", "workers")
    if os.path.exists(workers_dir):
        for root, dirs, files in os.walk(workers_dir):
            for f in files:
                assert not f.endswith(".bak"), f"Found .bak in worker dir: {os.path.join(root, f)}"


@step(r"the run completes successfully")
def then_run_completes_successfully(m, params):
    stdout = ctx.cli_result.stdout
    stderr = ctx.cli_result.stderr
    assert ctx.cli_result.returncode == 0, f"Run failed unexpectedly: {stdout}\n{stderr}"


@step(r'no worker run root remains under "\.mutate4py/workers/" after the run')
def then_worker_root_cleaned_up(m, params):
    workers_dir = os.path.join(os.path.realpath(ctx.project_dir), ".mutate4py", "workers")
    if os.path.exists(workers_dir):
        remaining = [e for e in os.listdir(workers_dir) if os.path.isdir(os.path.join(workers_dir, e))]
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


@step(r'the output does not contain "([^"]*)"')
def then_output_does_not_contain(m, params):
    msg = params.get("message") or m.group(1)
    combined = ctx.cli_result.stdout + ctx.cli_result.stderr
    assert msg not in combined, f"Unexpected '{msg}' in output:\n{combined}"


@step(r'no "Mutation Report" is printed')
def then_no_mutation_report(m, params):
    assert "Mutation Report" not in ctx.cli_result.stdout, f"Expected no 'Mutation Report' in:\n{ctx.cli_result.stdout}"


@step(r'no worker root is created under "\.mutate4py/workers/"')
def then_no_worker_root(m, params):
    workers_dir = os.path.join(os.path.realpath(ctx.project_dir), ".mutate4py", "workers")
    assert not os.path.exists(workers_dir), f"Worker dir was created: {workers_dir}"


@step(r"after the run the original source has no mutant spliced in")
def then_original_no_mutant(m, params):
    with open(ctx.src_path) as f:
        body = strip_manifest(f.read())
    # Byte for byte: the body above the manifest footer is what it was before the run.
    assert body == ctx.expected_body, f"source body differs from the pre-run body:\n{body!r}\n!=\n{ctx.expected_body!r}"


@step(r'the original source ends with a fresh "mutate4py-manifest" footer')
def then_manifest_footer(m, params):
    with open(ctx.src_path) as f:
        content = f.read()
    assert "mutate4py-manifest-begin" in content, f"No manifest footer in:\n{content}"


@step(r'no "\.mutate4py\.bak" file is left behind')
def then_no_bak(m, params):
    bak_path = ctx.src_path + ".bak"
    assert not os.path.exists(bak_path), f".bak file still present: {bak_path}"
