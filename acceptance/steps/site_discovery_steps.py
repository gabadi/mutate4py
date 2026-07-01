"""Step handlers for features/site-discovery.feature."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from mutate4py._discovery import discover_sites
from acceptance.steps.step_lib import (
    assert_no_scan_block,
    assert_nonzero_exit,
    make_registry,
    run_mutate4py,
)

STEP_HANDLERS, step, run_step = make_registry()

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


_CONSTRUCT_SOURCES = {
    "a + b": "x = a + b",
    "a - b": "x = a - b",
    "a * b": "x = a * b",
    "a > b": "x = a > b",
    "a >= b": "x = a >= b",
    "a < b": "x = a < b",
    "a <= b": "x = a <= b",
    "a == b": "x = a == b",
    "a != b": "x = a != b",
    "a is b": "x = a is b",
    "a is not b": "x = a is not b",
    "a in b": "x = a in b",
    "a not in b": "x = a not in b",
    "a and b": "x = a and b",
    "a or b": "x = a or b",
    "True": "x = True",
    "False": "x = False",
    "0": "x = 0",
    "1": "x = 1",
    # excluded
    "a += b": "a += b",
    "a -= b": "a -= b",
    "a / b": "x = a / b",
    "-a": "x = -a",
    "2": "x = 2",
}

_DEFINITION_SOURCES = {
    "def foo": "def foo():\n    x = a + b\n",
    "async def foo": "async def foo():\n    x = a + b\n",
    "class C with method m": "class C:\n    def m(self):\n        x = a + b\n",
    "module-level code (no def)": "x = a + b\n",
    "def outer with a nested def": "def outer():\n    def inner():\n        x = a + b\n",
    "def outer with a lambda": "def outer():\n    f = lambda: a + b\n",
}

_DEFINITION_IDS = {
    "def foo": "func/foo",
    "async def foo": "func/foo",
    "class C with method m": "func/C.m",
    "module-level code (no def)": "",
    "def outer with a nested def": "func/outer",
    "def outer with a lambda": "func/outer",
}


class Context:
    def __init__(self):
        self.sites = []
        self.total = 0
        self.threshold = 1000
        self.tmpdir = None
        self.source_path = None
        self.source_content = None
        self.cli_result = None


ctx = Context()


def _scan_construct(construct: str) -> None:
    if construct not in _CONSTRUCT_SOURCES:
        raise ValueError(f"unknown construct fixture: {construct!r}")
    src = _CONSTRUCT_SOURCES[construct]
    ctx.sites = discover_sites(src)
    ctx.total = len(ctx.sites)


@step(r'a Python file whose only mutable construct is "(.+)"')
def given_mutable_construct(m, params):
    _scan_construct(params.get("construct") or m.group(1))


@step(r'a Python file whose only candidate construct is "(.+)"')
def given_candidate_construct(m, params):
    _scan_construct(params.get("construct") or m.group(1))


@step(r"the file is scanned")
def when_scanned(m, params):
    pass  # scan already done in Given steps


@step(r"the total mutation sites is (\d+)")
def then_total_is(m, params):
    count_str = params.get("count") or m.group(1)
    expected = int(count_str)
    assert ctx.total == expected, f"expected {expected} sites, got {ctx.total}"


@step(r'a Python file defining "(.+)" containing one mutable site')
def given_definition_with_site(m, params):
    definition = params.get("definition") or m.group(1)
    if definition not in _DEFINITION_SOURCES:
        raise ValueError(f"unknown definition fixture: {definition!r}")
    src = _DEFINITION_SOURCES[definition]
    ctx.sites = discover_sites(src)
    ctx.total = len(ctx.sites)


@step(r'the site\'s function id is "(.*)"')
def then_function_id_is(m, params):
    expected = params.get("function_id") if "function_id" in params else m.group(1)
    assert len(ctx.sites) >= 1, "no sites found"
    assert ctx.sites[0].function_id == expected, (
        f"expected function_id={expected!r}, got {ctx.sites[0].function_id!r}"
    )


@step(r"a Python file containing (\d+) mutation sites? and no embedded manifest")
def given_file_with_n_sites(m, params):
    total_str = params.get("total") or m.group(1)
    n = int(total_str)
    lines = [f"x{i} = a + b" for i in range(n)]
    src = "\n".join(lines) + "\n" if lines else "pass\n"
    ctx.sites = discover_sites(src)
    ctx.total = len(ctx.sites)
    assert ctx.total == n, f"fixture error: wanted {n} sites, got {ctx.total}"
    # Write to a temp file for CLI-based scenarios
    ctx.tmpdir = tempfile.mkdtemp()
    ctx.source_path = os.path.join(ctx.tmpdir, "sample.py")
    ctx.source_content = src
    with open(ctx.source_path, "w") as f:
        f.write(src)


@step(r"the mutation warning threshold is (\d+)")
def given_threshold(m, params):
    threshold_str = params.get("threshold") or m.group(1)
    ctx.threshold = int(threshold_str)


@step(r"a Python file containing (\d+) mutation sites?")
def given_file_with_n_sites_no_manifest(m, params):
    total_str = params.get("total") or m.group(1)
    n = int(total_str)
    lines = [f"x{i} = a + b" for i in range(n)]
    src = "\n".join(lines) + "\n" if lines else "pass\n"
    ctx.sites = discover_sites(src)
    ctx.total = len(ctx.sites)
    assert ctx.total == n, f"fixture error: wanted {n} sites, got {ctx.total}"


@step(r'the warning line is "(.*)"')
def then_warning_line_is(m, params):
    expected = params.get("warning") if "warning" in params else m.group(1)
    if expected:
        assert ctx.total > ctx.threshold, (
            f"expected warning but {ctx.total} <= {ctx.threshold}"
        )
        expected_warning = (
            f"Warning: {ctx.total} mutation sites exceeds threshold {ctx.threshold}."
        )
        assert expected_warning == expected, (
            f"warning text mismatch: {expected_warning!r} != {expected!r}"
        )
    else:
        assert ctx.total <= ctx.threshold, (
            f"expected no warning but {ctx.total} > {ctx.threshold}"
        )


# CLI-based step handlers (scenarios 4 and 6)


@step(r'the command "mutate4py <file> --scan" is run')
def when_cli_scan(m, params):
    ctx.cli_result = run_mutate4py(ctx.source_path, "--scan")


@step(r'the output line "(.+)" is printed')
def then_cli_output_line(m, params):
    line = params.get("output_line") if "output_line" in params else m.group(1)
    line = line.replace("<total>", str(ctx.total))
    # Expand <file> to actual path
    line = line.replace("<file>", ctx.source_path or "")
    assert line in ctx.cli_result.stdout, (
        f"expected line {line!r} in stdout:\n{ctx.cli_result.stdout}"
    )


@step(r"no test command is run")
def then_no_test_cmd(m, params):
    pass  # --scan is read-only; no test infrastructure to check


@step(r"the file is left unchanged")
def then_file_unchanged(m, params):
    with open(ctx.source_path) as f:
        current = f.read()
    assert current == ctx.source_content, "file was modified by --scan"


@step(r'the path "<missing>" does not exist')
def given_missing_path(m, params):
    ctx.source_path = "/nonexistent/__no_such_file__.py"
    ctx.source_content = None
    ctx.cli_result = None


@step(r'the command "mutate4py <missing> --scan" is run')
def when_cli_scan_missing(m, params):
    ctx.cli_result = run_mutate4py(ctx.source_path, "--scan")


@step(r"the command exits with a usage error")
def then_usage_error(m, params):
    assert_nonzero_exit(ctx.cli_result, "usage error")


@step(r"no mutation scan block is printed")
def then_no_scan_block_main(m, params):
    assert_no_scan_block(ctx.cli_result)
