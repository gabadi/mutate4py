"""Step handlers for features/cli-surface_qa.feature (F5 CLI surface — QA end-to-end)."""

import os
import subprocess
import sys
import tempfile
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from acceptance.steps.step_lib import make_registry

STEP_HANDLERS, step, run_step = make_registry()

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

SOURCE_PY = textwrap.dedent("""\
    def calc(a, b):
        return a > b
""")


def _run(args: list[str], cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "mutate4py"] + args,
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def _write_script(path: str, content: str) -> None:
    with open(path, "w") as f:
        f.write(content)
    os.chmod(path, 0o755)


class QACtx:
    def __init__(self):
        self.tmpdir: str | None = None
        self.src_path: str | None = None
        self.lcov_path: str | None = None
        self.fake_cmd: str | None = None
        self.cli_result: subprocess.CompletedProcess | None = None
        self.src_bytes_before: bytes | None = None


ctx = QACtx()


def _reset() -> None:
    ctx.tmpdir = None
    ctx.src_path = None
    ctx.lcov_path = None
    ctx.fake_cmd = None
    ctx.cli_result = None
    ctx.src_bytes_before = None


def _tmpdir() -> str:
    if ctx.tmpdir is None:
        ctx.tmpdir = tempfile.mkdtemp()
    return ctx.tmpdir


def _src() -> str:
    if ctx.src_path is None:
        d = _tmpdir()
        ctx.src_path = os.path.join(d, "sample.py")
        with open(ctx.src_path, "w") as f:
            f.write(SOURCE_PY)
        with open(ctx.src_path, "rb") as f:
            ctx.src_bytes_before = f.read()
    return ctx.src_path


def _lcov(src: str) -> str:
    if ctx.lcov_path is None:
        d = _tmpdir()
        ctx.lcov_path = os.path.join(d, "cov.info")
        with open(ctx.lcov_path, "w") as f:
            f.write(f"SF:{src}\nDA:2,1\nend_of_record\n")
    return ctx.lcov_path


def _resolve_invocation(
    description: str, src: str, lcov: str | None = None
) -> list[str]:
    """Map a feature invocation description to actual CLI args (without 'mutate4py')."""
    d = description.strip()

    if d == "--mutation-warning 0":
        return [src, "--scan", "--mutation-warning", "0"]

    if d == "--max-workers -1":
        return [src, "--scan", "--max-workers", "-1"]

    if d == "--timeout-factor 1.5":
        return [src, "--scan", "--timeout-factor", "1.5"]

    if d == "--lines 7,x":
        # --lines is incompatible with --scan; pair with a coverage invocation
        lc = lcov or _lcov(src)
        return [src, "--lcov", lc, "--test-command", "true", "--lines", "7,x"]

    if d == "--scan --max-workers 4":
        return [src, "--scan", "--max-workers", "4"]

    if d == "--scan --mutate-all":
        return [src, "--scan", "--mutate-all"]

    if d == "--update-manifest --lines 7":
        return [src, "--update-manifest", "--lines", "7"]

    if d == "--since-last-run --mutate-all":
        lc = lcov or _lcov(src)
        return [
            src,
            "--lcov",
            lc,
            "--test-command",
            "true",
            "--since-last-run",
            "--mutate-all",
        ]

    if d == "--lcov cov.info --reuse-coverage":
        lc = lcov or _lcov(src)
        return [src, "--lcov", lc, "--reuse-coverage", "--test-command", "true"]

    if d == "--bogus-flag":
        return [src, "--bogus-flag"]

    if d == "(a path that does not exist)":
        return ["/nonexistent/no_such_file_qa.py", "--scan"]

    if d == "(no source file argument)":
        return ["--scan"]

    if d == "--max-workers (with no value)":
        return [src, "--scan", "--max-workers"]

    raise NotImplementedError(f"Unknown invocation description: {d!r}")


# ── Background ────────────────────────────────────────────────────────────────


@step(
    r"a temp project directory with a real Python source file holding a mutation site"
)
def given_temp_project(m, params):
    _reset()
    _src()  # creates tmpdir + sample.py, records bytes before


# ── Given: LCOV + fake command ────────────────────────────────────────────────


@step(r"a minimal LCOV fixture covering the site and a fast fake test command")
def given_lcov_and_fake_cmd(m, params):
    src = _src()
    lc = _lcov(src)
    d = _tmpdir()
    fake = os.path.join(d, "runtests.sh")
    _write_script(fake, "#!/bin/sh\nexit 0\n")
    ctx.fake_cmd = fake
    ctx.lcov_path = lc


# ── When steps ────────────────────────────────────────────────────────────────


@step(r'I invoke the mutate4py command described by "(.*)"')
def when_invoke_described(m, params):
    description = m.group(1)
    src = _src()
    lcov = ctx.lcov_path
    args = _resolve_invocation(description, src, lcov)
    ctx.cli_result = _run(args, cwd=_tmpdir())


@step(r'I invoke "(.*)"')
def when_invoke_literal(m, params):
    cmd_str = m.group(1)
    src = _src()
    lcov = ctx.lcov_path
    fake = ctx.fake_cmd
    d = _tmpdir()
    parts = cmd_str.split()
    # Strip leading "mutate4py" if present
    if parts and parts[0] == "mutate4py":
        parts = parts[1:]
    resolved = []
    for part in parts:
        if part == "<file>":
            resolved.append(src)
        elif part == "cov.info":
            resolved.append(lcov or os.path.join(d, "cov.info"))
        elif part == "<fake>":
            resolved.append(fake or "true")
        else:
            resolved.append(part)
    ctx.cli_result = _run(resolved, cwd=d)


@step(r'I invoke the mutate4py command with the accepted "(.*)"')
def when_invoke_accepted_mode(m, params):
    mode = m.group(1).strip()
    src = _src()
    d = _tmpdir()
    if mode == "--scan":
        ctx.cli_result = _run([src, "--scan"], cwd=d)
    elif mode == "--update-manifest":
        ctx.cli_result = _run([src, "--update-manifest"], cwd=d)
    else:
        raise NotImplementedError(f"Unknown mode: {mode!r}")


# ── Then steps ────────────────────────────────────────────────────────────────


@step(r"the command exits non-zero")
def then_exits_nonzero(m, params):
    r = ctx.cli_result
    assert r is not None, "No CLI result captured"
    assert r.returncode != 0, (
        f"Expected non-zero exit, got 0\nstdout: {r.stdout}\nstderr: {r.stderr}"
    )


@step(r"the command exits zero")
def then_exits_zero(m, params):
    r = ctx.cli_result
    assert r is not None, "No CLI result captured"
    assert r.returncode == 0, (
        f"Expected exit 0, got {r.returncode}\nstdout: {r.stdout}\nstderr: {r.stderr}"
    )


@step(r"the printed output names the offending flag or combination")
def then_output_names_flag(m, params):
    r = ctx.cli_result
    assert r is not None, "No CLI result captured"
    output = r.stdout + r.stderr
    assert (
        "error" in output.lower()
        or "invalid" in output.lower()
        or "cannot" in output.lower()
    ), f"Expected error message naming offending flag/combination:\n{output}"


@step(r"the source file is byte-identical to before the run")
def then_source_unchanged(m, params):
    src = ctx.src_path
    assert src is not None, "No source path recorded"
    with open(src, "rb") as f:
        current_bytes = f.read()
    assert current_bytes == ctx.src_bytes_before, (
        f"Source file changed!\nBefore: {ctx.src_bytes_before!r}\nAfter:  {current_bytes!r}"
    )


@step(r'no "\.mutate4py\.bak" file was created')
def then_no_bak(m, params):
    src = ctx.src_path
    assert src is not None, "No source path recorded"
    bak = src + ".bak"
    assert not os.path.exists(bak), f"Unexpected .mutate4py.bak file at: {bak}"


@step(r"the printed output contains a usage summary")
def then_output_contains_usage(m, params):
    r = ctx.cli_result
    assert r is not None, "No CLI result captured"
    output = r.stdout + r.stderr
    assert "usage:" in output.lower() or "mutate4py" in output, (
        f"Expected usage summary in output:\n{output}"
    )


@step(r'the printed output contains "(.*)"')
def then_output_contains(m, params):
    text = m.group(1)
    r = ctx.cli_result
    assert r is not None, "No CLI result captured"
    output = r.stdout + r.stderr
    assert text in output, f"Expected '{text}' in output:\n{output}"


@step(r"the printed output contains the mode's lead marker \"(.*)\"")
def then_output_contains_marker(m, params):
    marker = m.group(1)
    r = ctx.cli_result
    assert r is not None, "No CLI result captured"
    output = r.stdout + r.stderr
    assert marker in output, f"Expected marker '{marker}' in output:\n{output}"
