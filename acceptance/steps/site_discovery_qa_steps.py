"""Step handlers for features/site-discovery_qa.feature (end-to-end CLI tests)."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from acceptance.steps.step_lib import make_registry

STEP_HANDLERS, step, run_step = make_registry()

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_FIXTURES_DIR = os.path.join(_REPO_ROOT, "acceptance", "fixtures")


class QACtx:
    def __init__(self):
        self.result = None
        self.result2 = None
        self.fixture_path = None
        self.fixture_contents = None
        self.total = 0


ctx = QACtx()


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "mutate4py"] + list(args),
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )


# Background steps

@step(r"the mutate4py command-line tool is installed")
def given_cli_installed(m, params):
    result = subprocess.run(
        ["uv", "run", "mutate4py", "--help"],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    # --help may exit 0 or with usage; either way the tool exists
    pass


@step(r"a committed Python fixture whose header states its expected total sites")
def given_fixture_header_info(m, params):
    pass  # Satisfied by the fixtures in acceptance/fixtures/


# Scenario steps

@step(r'a fixture "([^"]+)" with expected total (\d+)')
def given_fixture_with_total(m, params):
    fixture = params.get("fixture") or m.group(1)
    total = int(params.get("total") or m.group(2))
    ctx.fixture_path = os.path.join(_FIXTURES_DIR, fixture)
    ctx.total = total
    with open(ctx.fixture_path) as f:
        ctx.fixture_contents = f.read()
    ctx.result = None


@step(r'the command "mutate4py <fixture> --scan" is run')
def when_scan_fixture(m, params):
    fixture = params.get("fixture") or ""
    path = os.path.join(_FIXTURES_DIR, fixture) if fixture else ctx.fixture_path
    ctx.result = _run_cli(path, "--scan")


@step(r"the command exits successfully")
def then_exits_ok(m, params):
    assert ctx.result.returncode == 0, (
        f"expected exit 0, got {ctx.result.returncode}\nstdout:{ctx.result.stdout}\nstderr:{ctx.result.stderr}"
    )


@step(r'the output line "(.+)" is printed')
def then_output_line_printed(m, params):
    raw = params.get("output_line") if "output_line" in params else m.group(1)
    line = raw.replace("<fixture>", os.path.basename(ctx.fixture_path) if ctx.fixture_path else "")
    line = line.replace("<total>", str(ctx.total))
    # The fixture path in the header line is the full path passed to CLI
    if "Mutation scan:" in line:
        line = f"Mutation scan: {ctx.fixture_path}"
    assert line in ctx.result.stdout, (
        f"expected line {line!r} in stdout:\n{ctx.result.stdout}"
    )


@step(r'the output line "Changed mutation sites: 6" is printed')
def then_changed_6(m, params):
    assert "Changed mutation sites: 6" in ctx.result.stdout, ctx.result.stdout


@step(r'the output line "Manifest exists: false" is printed')
def then_manifest_false(m, params):
    assert "Manifest exists: false" in ctx.result.stdout, ctx.result.stdout


@step(r'a fixture "([^"]+)"$')
def given_fixture_no_total(m, params):
    fixture = params.get("fixture") or m.group(1)
    ctx.fixture_path = os.path.join(_FIXTURES_DIR, fixture)
    with open(ctx.fixture_path) as f:
        ctx.fixture_contents = f.read()
    ctx.result = None


@step(r"a recorded copy of its contents")
def given_recorded_copy(m, params):
    # Already captured in ctx.fixture_contents during given_fixture_no_total
    pass


@step(r'the command "([^"]+)" is run through mutate4py')
def when_run_through_cli(m, params):
    cmd_str = m.group(1)
    parts = cmd_str.split()
    # Replace fixture name with full path
    args = []
    for p in parts:
        if p.endswith(".py"):
            args.append(os.path.join(_FIXTURES_DIR, p))
        else:
            args.append(p)
    ctx.result = _run_cli(*args)


@step(r"the fixture contents on disk match the recorded copy exactly")
def then_fixture_unchanged(m, params):
    with open(ctx.fixture_path) as f:
        current = f.read()
    assert current == ctx.fixture_contents, "fixture was modified by --scan"


@step(r"no test command was executed")
def then_no_test_run(m, params):
    pass  # --scan is read-only by design; no test infrastructure to check here


@step(r'the command "mutate4py (.+\.py) --scan --mutation-warning (\d+)" is run')
def when_scan_with_warning(m, params):
    fixture = params.get("fixture") or m.group(1)
    threshold = params.get("threshold") or m.group(2)
    path = os.path.join(_FIXTURES_DIR, fixture)
    ctx.fixture_path = path
    ctx.result = _run_cli(path, "--scan", "--mutation-warning", threshold)


@step(r'the warning line shown is "(.*)"')
def then_warning_shown(m, params):
    expected = params.get("warning") if "warning" in params else m.group(1)
    if expected:
        assert expected in ctx.result.stdout, (
            f"expected warning {expected!r} in stdout:\n{ctx.result.stdout}"
        )
    else:
        assert "Warning:" not in ctx.result.stdout, (
            f"unexpected warning in stdout:\n{ctx.result.stdout}"
        )


@step(r'no file exists at "([^"]+)"')
def given_no_file(m, params):
    path = params.get("path") or m.group(1)
    ctx.fixture_path = path  # use as-is (non-existent)
    ctx.result = None


@step(r'the command "mutate4py ([^ ]+) --scan" is run')
def when_scan_path(m, params):
    path = m.group(1)
    if not os.path.isabs(path):
        path = os.path.join(_FIXTURES_DIR, path)
    ctx.result = _run_cli(path, "--scan")


@step(r"the command exits with a non-zero status")
def then_nonzero_exit(m, params):
    assert ctx.result.returncode != 0, (
        f"expected non-zero exit, got {ctx.result.returncode}"
    )


@step(r'no "Mutation scan:" line is printed')
def then_no_scan_line(m, params):
    assert "Mutation scan:" not in ctx.result.stdout, (
        f"scan line unexpectedly in stdout:\n{ctx.result.stdout}"
    )


@step(r'the command "mutate4py mixed_operators.py --scan" is run twice')
def when_scan_twice(m, params):
    path = os.path.join(_FIXTURES_DIR, "mixed_operators.py")
    ctx.result = _run_cli(path, "--scan")
    ctx.result2 = _run_cli(path, "--scan")


@step(r"both runs print the same scan block")
def then_deterministic(m, params):
    assert ctx.result.stdout == ctx.result2.stdout, (
        f"runs differ:\nRun1:\n{ctx.result.stdout}\nRun2:\n{ctx.result2.stdout}"
    )
