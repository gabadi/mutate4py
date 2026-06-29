"""Step handlers for features/manifest_qa.feature (end-to-end CLI tests)."""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from acceptance.steps.step_lib import make_registry, run_mutate4py

STEP_HANDLERS, step, run_step = make_registry()

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_FIXTURES_DIR = os.path.join(_REPO_ROOT, "acceptance", "fixtures")


class Ctx:
    def __init__(self):
        self.result = None
        self.tmpdir = None
        self.work_path = None  # path to the writable copy
        self.recorded_bytes = None
        self.fixture_name = None

    def setup_copy(self, fixture_name: str) -> None:
        if self.tmpdir is None or not os.path.isdir(self.tmpdir):
            self.tmpdir = tempfile.mkdtemp(prefix="manifest_qa_")
        self.fixture_name = fixture_name
        src = os.path.join(_FIXTURES_DIR, fixture_name)
        self.work_path = os.path.join(self.tmpdir, fixture_name)
        shutil.copy2(src, self.work_path)
        self.result = None
        self.recorded_bytes = None


ctx = Ctx()


# ── Background ────────────────────────────────────────────────────────────────


@step(r"the mutate4py command-line tool is installed")
def given_cli_installed(m, params):
    run_mutate4py("--help")


@step(r"a writable copy of a committed Python fixture")
def given_writable_copy(m, params):
    pass  # satisfied per-scenario by the fixture steps below


# ── Given steps ───────────────────────────────────────────────────────────────


@step(r'a fixture copy "([^"]+)" with no embedded manifest')
def given_no_manifest(m, params):
    fixture = params.get("fixture") or m.group(1)
    ctx.setup_copy(fixture)
    # plain.py has no manifest by construction; assert to be safe
    text = open(ctx.work_path).read()
    assert "# mutate4py-manifest-begin" not in text, (
        f"fixture {fixture!r} unexpectedly contains a manifest"
    )


@step(r'a fixture copy "([^"]+)" that already has a current embedded manifest')
def given_already_current(m, params):
    fixture = params.get("fixture") or m.group(1)
    ctx.setup_copy(fixture)
    # Run --update-manifest once to embed a fresh manifest
    r = run_mutate4py(ctx.work_path, "--update-manifest")
    assert r.returncode == 0, f"pre-run failed: {r.stderr}"
    assert f"Updated manifest: {ctx.work_path}" in r.stdout, r.stdout


@step(r'a fixture copy "([^"]+)" with a current embedded manifest')
def given_current_manifest(m, params):
    fixture = params.get("fixture") or m.group(1)
    ctx.setup_copy(fixture)
    r = run_mutate4py(ctx.work_path, "--update-manifest")
    assert r.returncode == 0, f"pre-run failed: {r.stderr}"
    assert f"Updated manifest: {ctx.work_path}" in r.stdout, r.stdout


@step(r"a recorded copy of its bytes")
def given_recorded_bytes(m, params):
    ctx.recorded_bytes = open(ctx.work_path, "rb").read()


@step(r"the fixture copy is edited to change an operator")
def given_edit_operator(m, params):
    text = open(ctx.work_path).read()
    # Replace 'return a + b' with 'return a - b' (or 'return a - b' → 'return a + b')
    if "return a + b" in text:
        text = text.replace("return a + b", "return a - b", 1)
    elif "return a - b" in text:
        text = text.replace("return a - b", "return a + b", 1)
    else:
        # Generic: find first arithmetic operator on a return line and flip it
        import re

        text = re.sub(r"(return\s+\w+\s*)\+(\s*\w+)", r"\1-\2", text, count=1)
    open(ctx.work_path, "w").write(text)


@step(r"the fixture copy is edited by reformatting whitespace only")
def given_edit_whitespace(m, params):
    text = open(ctx.work_path).read()
    # Add an extra blank line at module level (above the manifest footer or at top)
    lines = text.split("\n")
    lines.insert(0, "")
    open(ctx.work_path, "w").write("\n".join(lines))


@step(r'a fixture copy "([^"]+)" with an embedded manifest that is out of date')
def given_stale_manifest(m, params):
    fixture = params.get("fixture") or m.group(1)
    ctx.setup_copy(fixture)
    text = open(ctx.work_path).read()
    assert "# mutate4py-manifest-begin" in text, (
        f"fixture {fixture!r} has no manifest to be stale"
    )


@step(r'no file exists at "([^"]+)"')
def given_no_file(m, params):
    path = params.get("path") or m.group(1)
    ctx.work_path = path
    ctx.fixture_name = path
    ctx.result = None


# ── When steps ────────────────────────────────────────────────────────────────


@step(r'the command "mutate4py ([^ ]+) --update-manifest" is run')
def when_update_manifest(m, params):
    raw_path = params.get("path") or m.group(1)
    # Replace the fixture name placeholder with the actual work path
    if ctx.work_path and os.path.basename(ctx.work_path) == raw_path:
        path = ctx.work_path
    elif ctx.work_path and raw_path == os.path.basename(ctx.work_path):
        path = ctx.work_path
    else:
        path = ctx.work_path or raw_path
    ctx.result = run_mutate4py(path, "--update-manifest")


# ── Then steps ────────────────────────────────────────────────────────────────


@step(r"the command exits successfully")
def then_exits_ok(m, params):
    assert ctx.result.returncode == 0, (
        f"expected exit 0, got {ctx.result.returncode}\n"
        f"stdout:{ctx.result.stdout}\nstderr:{ctx.result.stderr}"
    )


@step(r"the command exits with a non-zero status")
def then_nonzero_exit(m, params):
    assert ctx.result.returncode != 0, (
        f"expected non-zero exit, got {ctx.result.returncode}\n"
        f"stdout:{ctx.result.stdout}"
    )


@step(r'the output line "([^"]+)" is printed')
def then_output_line(m, params):
    raw = params.get("output_line") if "output_line" in params else m.group(1)
    # Replace the fixture filename placeholder with the actual work path
    line = raw.replace(
        os.path.basename(ctx.work_path) if ctx.work_path else "",
        ctx.work_path or "",
    )
    assert line in ctx.result.stdout, (
        f"expected {line!r} in stdout:\n{ctx.result.stdout}"
    )


@step(r'the file "([^"]+)" then contains a "([^"]+)" line')
def then_file_contains_line(m, params):
    filename = params.get("filename") or m.group(1)
    marker = params.get("marker") or m.group(2)
    path = (
        ctx.work_path
        if ctx.work_path and os.path.basename(ctx.work_path) == filename
        else filename
    )
    text = open(path).read()
    assert marker in text, f"expected {marker!r} in file {path!r}"


@step(r'the file "([^"]+)" on disk matches the recorded bytes exactly')
def then_bytes_match(m, params):
    filename = params.get("filename") or m.group(1)
    path = (
        ctx.work_path
        if ctx.work_path and os.path.basename(ctx.work_path) == filename
        else filename
    )
    current = open(path, "rb").read()
    assert current == ctx.recorded_bytes, (
        f"file changed: recorded {len(ctx.recorded_bytes)} bytes, "
        f"now {len(current)} bytes"
    )


@step(r'the file "([^"]+)" still contains exactly one "([^"]+)" line')
def then_file_one_occurrence(m, params):
    filename = params.get("filename") or m.group(1)
    marker = params.get("marker") or m.group(2)
    path = (
        ctx.work_path
        if ctx.work_path and os.path.basename(ctx.work_path) == filename
        else filename
    )
    text = open(path).read()
    count = text.count(marker)
    assert count == 1, f"expected exactly one {marker!r} in {path!r}, found {count}"


@step(r'no "Updated manifest:" line is printed')
def then_no_updated_line(m, params):
    assert "Updated manifest:" not in ctx.result.stdout, (
        f"unexpected 'Updated manifest:' in stdout:\n{ctx.result.stdout}"
    )


@step(r'no file is created at "([^"]+)"')
def then_no_file_created(m, params):
    path = params.get("path") or m.group(1)
    assert not os.path.exists(path), f"file unexpectedly exists at {path!r}"


@step(r'the file "([^"]+)" contains exactly one "([^"]+)" line')
def then_file_exactly_one(m, params):
    filename = params.get("filename") or m.group(1)
    marker = params.get("marker") or m.group(2)
    path = (
        ctx.work_path
        if ctx.work_path and os.path.basename(ctx.work_path) == filename
        else filename
    )
    text = open(path).read()
    count = text.count(marker)
    assert count == 1, f"expected exactly one {marker!r} in {path!r}, found {count}"
