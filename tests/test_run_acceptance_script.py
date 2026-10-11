"""run_acceptance.sh refuses to run without gherkin-parser (#83)."""

import shutil
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "acceptance" / "run_acceptance.sh"
_BASH4_CANDIDATES = ("/opt/homebrew/bin/bash", "/usr/local/bin/bash")


def _find_bash4():
    """A bash 4+ binary (run_acceptance.sh uses `declare -A`), or None."""
    for candidate in (shutil.which("bash"), *_BASH4_CANDIDATES):
        if candidate is None or not Path(candidate).is_file():
            continue
        probe = subprocess.run(
            [candidate, "-c", 'echo "${BASH_VERSINFO[0]}"'],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if probe.returncode == 0 and probe.stdout.strip().isdigit():
            if int(probe.stdout.strip()) >= 4:
                return candidate
    return None


@pytest.fixture
def bash4():
    path = _find_bash4()
    if path is None:
        pytest.skip("run_acceptance.sh needs bash 4+ (declare -A); none found on PATH or in Homebrew locations")
    return path


@pytest.mark.integration
def test_run_acceptance_fails_naming_gherkin_parser_when_missing(tmp_path, bash4):
    result = subprocess.run(
        [bash4, str(_SCRIPT)],
        env={"PATH": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "gherkin-parser not found" in result.stderr


@pytest.mark.integration
def test_run_acceptance_stops_when_gherkin_parser_fails(tmp_path, bash4):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_parser = fake_bin / "gherkin-parser"
    fake_parser.write_text("#!/bin/sh\necho 'parse error' >&2\nexit 1\n")
    fake_parser.chmod(0o755)
    result = subprocess.run(
        [bash4, str(_SCRIPT)],
        env={"PATH": f"{fake_bin}:/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "gherkin-parser failed on" in result.stderr
    assert "Acceptance summary" not in result.stdout
