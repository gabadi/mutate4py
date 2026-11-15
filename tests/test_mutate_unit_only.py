"""`just mutate` scores with unit tests only, and no test-context db (#98).

The scored loop reads neither LCOV nor the test-context db: the Measurement is
the Coverage gate and the narrowing source (#95, #96). So the `mutate` recipe
has no dependency, passes no coverage or test-context flag, and selects tests
with MUTATE_PYTEST_ARGS. The gate that checked the db (`context-deselection`)
and its script go with it.

Seams: the justfile's own parse (`just --dump`), `just check`'s gate-name
validation, the CI workflow text, AGENTS.md's `just mutate` bullet, pyproject's
pytest path, and the absence of the removed files.
"""

import json
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
JUSTFILE = REPO_ROOT / "justfile"
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
AGENTS_MD = REPO_ROOT / "AGENTS.md"
PYPROJECT = REPO_ROOT / "pyproject.toml"

REMOVED_GATE_RECIPES = ("context-deselection", "test-context-db")
# Flags that tickets 10-12 (#99-#101) remove from mutate4py. Nothing in the
# justfile or CI may pass one to mutate4py after this ticket.
REMOVED_MUTATE4PY_FLAGS = (
    "--lcov",
    "--cov-cmd",
    "--reuse-coverage",
    "--test-contexts",
    "--build-test-contexts",
    "--lines",
    "--since-last-run",
)


@pytest.fixture(scope="module")
def dump():
    just = shutil.which("just")
    if just is None:
        pytest.skip("just is not on PATH")
    result = subprocess.run(
        [just, "--dump", "--dump-format", "json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return json.loads(result.stdout)


def _render(fragment):
    """Flatten one body fragment: plain text, or an interpolation rendered as {{name}}."""
    if isinstance(fragment, str):
        return fragment
    if len(fragment) == 2 and fragment[0] == "variable":
        return "{{" + fragment[1] + "}}"
    return "".join(_render(child) for child in fragment)


def _body(dump, name):
    return "\n".join("".join(_render(fragment) for fragment in line) for line in dump["recipes"][name]["body"])


def _dependencies(dump, name):
    return [dep["recipe"] for dep in dump["recipes"][name]["dependencies"]]


def _assignment(dump, name):
    return dump["assignments"][name]["value"]


@pytest.mark.integration
def test_mutate_recipe_has_no_dependency_so_no_db_is_built_first(dump):
    assert _dependencies(dump, "mutate") == []


@pytest.mark.integration
def test_mutate_command_passes_no_lcov_or_test_context_flag(dump):
    body = _body(dump, "mutate")
    assert 'uv run mutate4py {{path}} --pytest-args "{{MUTATE_PYTEST_ARGS}}" {{args}}' in body
    for flag in REMOVED_MUTATE4PY_FLAGS:
        assert flag not in body, flag
    assert "TEST_CONTEXT_DB" not in body


@pytest.mark.integration
def test_mutate_pytest_args_select_unit_tests_only(dump):
    assert _assignment(dump, "MUTATE_PYTEST_ARGS") == "-p no:tach -m 'not integration and not component'"


@pytest.mark.integration
def test_test_context_db_recipe_and_variable_are_gone(dump):
    for name in REMOVED_GATE_RECIPES:
        assert name not in dump["recipes"], name
    assert "TEST_CONTEXT_DB" not in dump["assignments"]


@pytest.mark.integration
def test_check_gate_list_names_no_removed_gate(dump):
    body = _body(dump, "check")
    assert "context-deselection" not in body
    assert "test-context-db" not in body


@pytest.mark.integration
def test_check_rejects_a_removed_gate_name_before_running_anything():
    just = shutil.which("just")
    if just is None:
        pytest.skip("just is not on PATH")
    for name in REMOVED_GATE_RECIPES:
        # The unknown second name fails `check`'s validation loop before any
        # gate runs, so this never starts a real gate (test-context-db alone
        # would begin a ~16-minute db build).
        result = subprocess.run(
            [just, "check", name, "no-such-gate"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode != 0, name
        assert f"no such gate: {name}" in result.stderr, name
        gates_line = next((line for line in result.stderr.splitlines() if line.strip().startswith("gates:")), "")
        assert name not in gates_line.split(), name


@pytest.mark.integration
def test_mutate_sample_recipe_has_no_dependency_and_no_lcov(dump):
    assert _dependencies(dump, "mutate-sample") == []
    assert "lcov" not in _body(dump, "mutate-sample")


@pytest.mark.integration
def test_check_guard_for_lcov_readers_no_longer_names_mutate_sample(dump):
    # `mutate-sample` shells out to `mutate`, which reads no lcov.info now, so
    # the guard that required `test-unit` before it must be gone. `crap` is the
    # only lcov reader left.
    match = re.search(r"^\s*for needs_test in (.*); do$", _body(dump, "check"), re.MULTILINE)
    assert match, "check keeps a guard loop over the lcov readers"
    assert match.group(1).split() == ["crap"]


@pytest.mark.integration
def test_test_unit_still_writes_the_lcov_file_for_the_crap_gate(dump):
    assert "--cov-report=lcov:lcov.info" in _body(dump, "test-unit")


@pytest.mark.integration
def test_perf_runs_no_test_context_db_step_and_no_test_contexts_flag(dump):
    body = _body(dump, "perf")
    assert "test-context-db" not in body
    assert "--test-contexts" not in body


@pytest.mark.integration
def test_no_recipe_passes_a_removed_flag_to_mutate4py(dump):
    offenders = [
        (name, flag)
        for name in dump["recipes"]
        for line in _body(dump, name).splitlines()
        if "mutate4py" in line
        for flag in REMOVED_MUTATE4PY_FLAGS
        if flag in line
    ]
    assert offenders == []


def _mutate_header_comment():
    """The contiguous comment block directly above the `mutate` recipe."""
    lines = JUSTFILE.read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("mutate path *args:"))
    block = []
    for line in reversed(lines[:start]):
        if not line.startswith("#"):
            break
        block.append(line)
    return "\n".join(reversed(block))


@pytest.mark.unit
def test_mutate_header_comment_drops_the_lcov_test_contexts_and_db_paragraphs():
    header = _mutate_header_comment()
    assert header, "the mutate recipe has a header comment"
    for needle in ("lcov", "--test-contexts", "contexts.db", "test-context"):
        assert needle not in header, needle


@pytest.mark.unit
def test_agents_md_mutate_bullet_drops_the_test_context_db_sentence():
    bullet = next(line for line in AGENTS_MD.read_text().splitlines() if line.startswith("- `just mutate <path>"))
    for needle in ("test-context", "contexts.db", "builds-or-refreshes", "cold cache"):
        assert needle not in bullet, needle


@pytest.mark.unit
def test_removed_gate_script_and_its_test_are_deleted():
    assert not (REPO_ROOT / "scripts" / "check_context_deselection.py").exists()
    assert not (REPO_ROOT / "tests" / "test_check_context_deselection.py").exists()


@pytest.mark.unit
def test_pytest_no_longer_puts_scripts_on_the_path_for_the_removed_gate():
    config = tomllib.loads(PYPROJECT.read_text())
    assert "scripts" not in config["tool"]["pytest"]["ini_options"].get("pythonpath", [])


@pytest.mark.unit
def test_ci_names_no_context_deselection_or_test_context_db_step():
    text = CI_YML.read_text()
    assert "context-deselection" not in text
    assert "Context deselection" not in text
    assert "test-context-db" not in text


@pytest.mark.unit
def test_ci_keeps_the_unit_tests_and_crap_steps():
    text = CI_YML.read_text()
    assert re.search(r"^      - name: Tests \(unit\)\n\s+run: just test-unit$", text, re.MULTILINE)
    assert re.search(r"^      - name: CRAP\n\s+run: just crap$", text, re.MULTILINE)
