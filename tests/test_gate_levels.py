"""The test levels map to one gate and one CI step each (issue #122).

Unit (`test-unit`) is coverage-measured. System (`test-system`) runs real
processes with no coverage. The `test-component` and `test-integration` gates
and their CI steps are retired, so neither name may come back.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
JUSTFILE = REPO_ROOT / "justfile"
RETIRED_GATES = ("test-component", "test-integration")


def _recipe_lines(name):
    """The non-blank body lines of one justfile recipe, stripped."""
    lines = JUSTFILE.read_text().splitlines()
    start = lines.index(f"{name}:")
    body = []
    for line in lines[start + 1 :]:
        if line and not line.startswith(" "):
            break
        body.append(line.strip())
    return [line for line in body if line]


@pytest.mark.unit
def test_test_system_gate_runs_the_system_marker_without_coverage():
    assert _recipe_lines("test-system") == ["uv run pytest -m system -n auto -p no:tach --no-cov"]


@pytest.mark.unit
def test_check_gate_list_runs_test_system_after_test_unit():
    all_line = next(line.strip() for line in JUSTFILE.read_text().splitlines() if line.strip().startswith("all=("))
    gates = all_line.removeprefix("all=(").removesuffix(")").split()
    assert gates[:3] == ["lint", "format-check", "test-unit"]
    assert gates[3] == "test-system"


@pytest.mark.unit
def test_perf_times_the_system_gate_in_place_of_the_retired_two():
    body = "\n".join(_recipe_lines("perf"))
    assert "just --no-deps test-system" in body
    assert "test (system)" in body


@pytest.mark.unit
def test_ci_runs_one_system_step_between_unit_and_crap():
    text = CI_YML.read_text()
    assert re.search(r"^      - name: Tests \(system\)\n\s+run: just test-system$", text, re.MULTILINE)
    assert text.index("- name: Tests (unit)") < text.index("- name: Tests (system)") < text.index("- name: CRAP")


@pytest.mark.unit
def test_retired_gate_names_and_ci_steps_are_gone():
    for name in RETIRED_GATES:
        assert name not in JUSTFILE.read_text(), name
        assert name not in CI_YML.read_text(), name
    text = CI_YML.read_text()
    assert "Tests (component)" not in text
    assert "Tests (integration)" not in text
