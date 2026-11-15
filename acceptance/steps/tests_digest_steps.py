"""Step handlers for features/tests-digest.feature (the skip rule and recorded Survivors)."""

import atexit
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from acceptance.steps.nested_pytest_helpers import nested_pytest_env
from acceptance.steps.step_lib import make_registry
from acceptance.steps.tests_digest_helpers import (
    DIGEST_PROJECT_FILES,
    OTHER_AFTER,
    OTHER_BEFORE,
    RECORDED_HEADER,
    SURVIVOR_PROJECT_FILES,
    edited,
    recorded_survivor_ids,
    rescored_function_ids,
    survivor_ids,
    without_digests,
)

STEP_HANDLERS, step, run_step = make_registry()

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class Context:
    def __init__(self):
        self.root: str | None = None
        self.target: str = "src"
        self.cli_result: subprocess.CompletedProcess | None = None
        self.scored: list[str] = []


ctx = Context()


# Each project kind is written and scored once per process. A scenario starts from a copy of
# that scored state, so the identical first run is not repeated for every scenario. The cache
# holds only the copied-from projects; every scenario edits its own copy.
_SCORED: dict[str, tuple[str, subprocess.CompletedProcess]] = {}
_cache_root: str | None = None


def _project_cache_root() -> str:
    global _cache_root
    if _cache_root is None:
        _cache_root = tempfile.mkdtemp(prefix="tests_digest_cache_")
        atexit.register(shutil.rmtree, _cache_root, ignore_errors=True)
    return _cache_root


def _build_scored(kind: str, files: dict[str, str], target: str) -> tuple[str, subprocess.CompletedProcess]:
    """Write the project of `kind` into a fresh cache directory, score it once, and return that directory and the first run."""
    ctx.root = tempfile.mkdtemp(prefix=f"{kind}_", dir=_project_cache_root())
    ctx.target = target
    ctx.cli_result = None
    for rel, text in files.items():
        _write(rel, text)
    _score_project()
    return ctx.root, ctx.cli_result


def _write_project(kind: str, files: dict[str, str], target: str) -> None:
    """Give ctx a fresh copy of the project of `kind`, already scored once, with that first run as its result."""
    if kind not in _SCORED:
        _SCORED[kind] = _build_scored(kind, files, target)
    cache_dir, first = _SCORED[kind]
    ctx.root = tempfile.mkdtemp()
    shutil.copytree(cache_dir, ctx.root, dirs_exist_ok=True)
    ctx.target = target
    ctx.cli_result = first


def _write(rel: str, text: str) -> None:
    path = os.path.join(ctx.root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def _read(rel: str) -> str:
    with open(os.path.join(ctx.root, rel)) as f:
        return f.read()


def _run(*extra: str) -> subprocess.CompletedProcess:
    # --project REPO_ROOT pins resolution to this repo's own editable install: cwd is a scratch
    # tempdir outside the repo, so a bare "uv run mutate4py" could pick up any installed copy.
    return subprocess.run(
        ["uv", "run", "--project", REPO_ROOT, "python", "-m", "mutate4py", ctx.target, "--pytest-args", "tests", *extra],
        capture_output=True,
        text=True,
        cwd=ctx.root,
        env=nested_pytest_env(),
    )


def _shown() -> str:
    return f"stdout:\n{ctx.cli_result.stdout}\nstderr:\n{ctx.cli_result.stderr}"


def _score_project() -> None:
    first = _run()
    assert first.returncode in (0, 3), f"the first scored run failed\nstdout:\n{first.stdout}\nstderr:\n{first.stderr}"
    ctx.cli_result = first


# ── Given steps ──────────────────────────────────────────────────────────────


@step(r"a project of five modules, each with its own tests, scored once")
def given_digest_project(m, params):
    _write_project("digest", DIGEST_PROJECT_FILES, "src")
    ctx.scored = sorted(rescored_function_ids(ctx.cli_result.stdout))
    assert len(ctx.scored) == 6, _shown()
    assert ctx.cli_result.returncode == 0, _shown()


@step(r"a module whose two functions survive their tests, scored once")
def given_survivor_project(m, params):
    _write_project("survivor", SURVIVOR_PROJECT_FILES, "sur.py")
    assert survivor_ids(ctx.cli_result.stdout) == ["func/keep", "func/other"], _shown()
    assert ctx.cli_result.returncode == 3, _shown()


@step(r"the Manifest is stored as a 0\.2\.x run left it, with no tests digests")
def given_zero_two_manifest(m, params):
    _write(ctx.target, without_digests(_read(ctx.target)))


# ── When steps ───────────────────────────────────────────────────────────────


@step(r'the file "([^"]*)" is edited without changing what it does')
def when_file_edited(m, params):
    rel = m.group(1)
    _write(rel, edited(_read(rel)))


@step(r'the body of "other" in "sur\.py" is changed')
def when_other_changed(m, params):
    text = _read("sur.py")
    assert OTHER_BEFORE in text
    _write("sur.py", text.replace(OTHER_BEFORE, OTHER_AFTER))


@step(r"mutate4py is run again")
def when_run_again(m, params):
    ctx.cli_result = _run()


@step(r'mutate4py is run again with "--allow-survivors"')
def when_run_again_allow(m, params):
    ctx.cli_result = _run("--allow-survivors")


@step(r'mutate4py is run with "--help"')
def when_help(m, params):
    ctx.cli_result = subprocess.run(
        ["uv", "run", "--project", REPO_ROOT, "python", "-m", "mutate4py", "--help"],
        capture_output=True,
        text=True,
        cwd=ctx.root or REPO_ROOT,
        env=nested_pytest_env(),
    )


@step(r'mutate4py is run again with "--check-manifest"')
def when_check_manifest(m, params):
    ctx.cli_result = subprocess.run(
        ["uv", "run", "--project", REPO_ROOT, "python", "-m", "mutate4py", ctx.target, "--check-manifest"],
        capture_output=True,
        text=True,
        cwd=ctx.root,
        env=nested_pytest_env(),
    )


# ── Then steps ───────────────────────────────────────────────────────────────


@step(r"the functions re-scored are (.*)")
def then_rescored(m, params):
    wanted = [name.strip().strip('"') for name in m.group(1).split(",")]
    got = sorted(rescored_function_ids(ctx.cli_result.stdout))
    assert got == sorted(wanted), f"re-scored {got}, wanted {sorted(wanted)}\n{_shown()}"


@step(r"every function is re-scored")
def then_everything_rescored(m, params):
    got = sorted(rescored_function_ids(ctx.cli_result.stdout))
    assert got == ctx.scored, f"re-scored {got}, wanted every scored function {ctx.scored}\n{_shown()}"


@step(r"no function is re-scored")
def then_nothing_rescored(m, params):
    got = rescored_function_ids(ctx.cli_result.stdout)
    assert got == [], f"re-scored {got}, wanted nothing\n{_shown()}"


@step(r"the exit code is (\d+)")
def then_exit_code(m, params):
    expected = int(m.group(1))
    assert ctx.cli_result.returncode == expected, f"Expected exit {expected}, got {ctx.cli_result.returncode}\n{_shown()}"


@step(r'the Survivors block names only "([^"]*)"')
def then_survivors_block(m, params):
    assert survivor_ids(ctx.cli_result.stdout) == [m.group(1)], _shown()


@step(r'the recorded Survivors block names only "([^"]*)"')
def then_recorded_only(m, params):
    assert recorded_survivor_ids(ctx.cli_result.stdout) == [m.group(1)], _shown()


@step(r'the recorded Survivors block names "([^"]*)" and "([^"]*)"')
def then_recorded_two(m, params):
    assert recorded_survivor_ids(ctx.cli_result.stdout) == [m.group(1), m.group(2)], _shown()


@step(r"there is no recorded Survivors block")
def then_no_recorded(m, params):
    assert RECORDED_HEADER not in ctx.cli_result.stdout, _shown()


@step(r'the "--check-manifest" help states it checks hashes, Survivors and markers, not tests digests')
def then_help_states(m, params):
    text = ctx.cli_result.stdout
    flat = " ".join(text.split())
    assert "Verify the manifest footer is up to date" in flat, text
    assert "hashes, recorded Survivors and equivalent markers, not tests digests" in flat, text
