"""`just check` fails fast when a gate's external tool is missing (#112).

drywall (the `dry` gate) and gherkin-parser (the `acceptance` gate) are not
Python packages, so nothing else notices they are absent until the gate fails
with exit 127. The preflight runs before the first gate, names the tool, and
names the recipe that installs it.
"""

import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_FAST_ENOUGH_SECONDS = 30


@pytest.fixture
def just_bin():
    path = shutil.which("just")
    if path is None:
        pytest.skip("just is not on PATH")
    return path


@pytest.fixture
def bare_env(tmp_path, just_bin):
    """PATH holds only `just`; HOME is empty, so ~/.local/bin holds no tools."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "just").symlink_to(just_bin)
    home = tmp_path / "home"
    home.mkdir()
    return {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(home), "TMPDIR": str(tmp_path)}


def _just(just_bin, env, *args):
    started = time.monotonic()
    result = subprocess.run(
        [just_bin, *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result, time.monotonic() - started


@pytest.mark.integration
def test_check_names_missing_drywall_and_install_recipe_before_the_gate_runs(just_bin, bare_env):
    result, elapsed = _just(just_bin, bare_env, "check", "dry")

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "drywall" in output
    assert "just install-tools" in output
    assert elapsed < _FAST_ENOUGH_SECONDS


@pytest.mark.integration
def test_check_names_missing_gherkin_parser_and_install_recipe(just_bin, bare_env):
    result, elapsed = _just(just_bin, bare_env, "check", "acceptance")

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "gherkin-parser" in output
    assert "just install-tools" in output
    assert elapsed < _FAST_ENOUGH_SECONDS


@pytest.mark.integration
def test_full_check_reports_both_missing_tools_and_runs_no_gate(just_bin, bare_env):
    result, elapsed = _just(just_bin, bare_env, "check")

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "drywall" in output
    assert "gherkin-parser" in output
    assert "just install-tools" in output
    assert "✓" not in output
    assert elapsed < _FAST_ENOUGH_SECONDS


@pytest.mark.integration
def test_check_runs_the_gate_once_its_tool_is_present(just_bin, bare_env, tmp_path):
    fake_drywall = Path(bare_env["PATH"].split(":")[0]) / "drywall"
    fake_drywall.write_text("#!/bin/sh\nexit 0\n")
    fake_drywall.chmod(0o755)

    result, _ = _just(just_bin, bare_env, "--set", "LOG", str(tmp_path / "check.log"), "check", "dry")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "✓ dry" in result.stdout


@pytest.mark.integration
def test_gates_that_need_no_tool_pass_the_preflight(just_bin, bare_env):
    result, _ = _just(just_bin, bare_env, "require-tools", "lint", "format-check", "test-unit")

    assert result.returncode == 0, result.stdout + result.stderr
