"""CI installs drywall and gherkin-parser through `just install-tools` (#112).

CI and local runs must read one set of pins. The pins live in the justfile, so
ci.yml may not restate them, and it may not carry its own download or build.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
JUSTFILE = REPO_ROOT / "justfile"


def _pin(name):
    match = re.search(rf'^{name} := "([^"]+)"$', JUSTFILE.read_text(), re.MULTILINE)
    assert match, f"justfile defines no {name} pin"
    return match.group(1)


def _step(name):
    """Return the body of one workflow step: everything after its `- name:` line, up to the next step."""
    text = CI_YML.read_text()
    match = re.search(
        rf"^      - name: {re.escape(name)}\n(.*?)(?=^      - |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"ci.yml has no step named {name!r}"
    return match.group(1)


@pytest.mark.unit
def test_install_step_calls_the_justfile_recipe():
    assert "just install-tools" in _step("Install tools")


@pytest.mark.unit
def test_install_step_puts_local_bin_on_path_for_later_steps():
    assert re.search(r'\$HOME/\.local/bin"?\s*>>\s*"?\$GITHUB_PATH', _step("Install tools"))


@pytest.mark.unit
def test_install_step_runs_before_dry_and_acceptance():
    text = CI_YML.read_text()
    install = text.index("- name: Install tools")
    assert install < text.index("- name: DRY") < text.index("- name: Acceptance tests")


@pytest.mark.unit
def test_ci_restates_no_pin_or_install_command():
    text = CI_YML.read_text()
    restated = [
        _pin("DRYWALL_TAG"),
        _pin("GHERKIN_PARSER_COMMIT"),
        "gh release download",
        "go build",
        "git clone",
        "/usr/local/bin",
        "DRYWALL: ./drywall",
    ]
    assert [needle for needle in restated if needle in text] == []


@pytest.mark.unit
def test_dry_step_still_calls_just_dry_and_needs_no_drywall_env():
    step = _step("DRY")
    assert "run: just dry" in step
    assert "DRYWALL" not in step
