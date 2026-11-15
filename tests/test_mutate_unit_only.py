"""`just mutate` scores with unit tests only, and no test-context db (#98).

The scored loop reads neither LCOV nor the test-context db: the Measurement is
the Coverage gate and the narrowing source (#95, #96). The `mutate` recipe
passes no coverage or test-context flag and selects tests with
MUTATE_PYTEST_ARGS. The checks that a removed recipe or file stays removed were
deleted along with those removals.

Seams: the justfile's own parse (`just --dump`) and the CI workflow text.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"

# Flags that tickets 10-12 (#99-#101) remove from mutate4py. Nothing in the
# justfile may pass one to mutate4py after this ticket.
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


def _assignment(dump, name):
    return dump["assignments"][name]["value"]


@pytest.mark.system
def test_mutate_command_passes_no_lcov_or_test_context_flag(dump):
    body = _body(dump, "mutate")
    assert 'uv run mutate4py {{path}} --pytest-args "{{MUTATE_PYTEST_ARGS}}" {{args}}' in body
    for flag in REMOVED_MUTATE4PY_FLAGS:
        assert flag not in body, flag
    assert "TEST_CONTEXT_DB" not in body


@pytest.mark.system
def test_mutate_pytest_args_select_unit_tests_only(dump):
    assert _assignment(dump, "MUTATE_PYTEST_ARGS") == "-p no:tach -m unit"


@pytest.mark.system
def test_test_unit_still_writes_the_lcov_file_for_the_crap_gate(dump):
    assert "--cov-report=lcov:lcov.info" in _body(dump, "test-unit")


@pytest.mark.unit
def test_ci_keeps_the_unit_tests_and_crap_steps():
    text = CI_YML.read_text()
    assert re.search(r"^      - name: Tests \(unit\)\n\s+run: just test-unit$", text, re.MULTILINE)
    assert re.search(r"^      - name: CRAP\n\s+run: just crap$", text, re.MULTILINE)
