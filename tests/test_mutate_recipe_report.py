"""`just mutate` shows what a run decided and keeps this repo's Manifests in their sidecars (#110).

Found verifying spec 89's AC-2 and AC-2b with the literal `just mutate <file>`:
- src/ stores every Manifest as a sidecar, so a run without `--manifest-file` ignores the
  sidecar (scoring the whole file as if it had no Manifest) and embeds a second Manifest
  in the source;
- a skipped run (no Measurement) prints no `Mutation Report`, so the recipe's filter
  printed nothing, hiding the skipped line and the recorded Survivors behind exit 3.

Seams: the justfile's own parse (`just --dump`), and the recipe's report filter run as
bash over the lines mutate4py prints.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from mutate4py._skipped_run import SKIPPED_MEASUREMENT_LINE, skipped_run_report

REPO_ROOT = Path(__file__).resolve().parent.parent

_SURVIVOR = {"line": 28, "desc": "returncode > 128 -> returncode >= 128"}


@pytest.fixture(scope="module")
def mutate_body():
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
    lines = json.loads(result.stdout)["recipes"]["mutate"]["body"]
    return ["".join(part if isinstance(part, str) else "" for part in line) for line in lines]


def _filter(mutate_body, log_text: str, tmp_path) -> str:
    """Run the recipe's report filter line over log_text, as the recipe runs it over its log."""
    line = next(text for text in mutate_body if re.match(r"\s*awk ", text))
    log = tmp_path / "run.log"
    log.write_text(log_text)
    script = f'log="{log}"\n{line.strip()}\n'
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True, timeout=30).stdout


@pytest.mark.system
def test_mutate_recipe_stores_the_manifest_as_a_sidecar(mutate_body):
    command = next(text for text in mutate_body if "uv run mutate4py" in text)
    assert "--manifest-file" in command.split()


@pytest.mark.system
def test_report_filter_shows_a_skipped_run_and_its_recorded_survivors(mutate_body, tmp_path):
    entry = {
        "id": "func/classify_exit_code",
        "score": {"killed": 2, "survived": 1, "uncovered": 0},
        "survivors": [_SURVIVOR],
        "accepted": [],
    }
    manifest = {"functions": [entry]}
    lines, code = skipped_run_report([(str(tmp_path / "m.py"), manifest)], cwd=str(tmp_path), allow_survivors=False)
    assert code == 3

    shown = _filter(mutate_body, "uv progress noise\n" + "\n".join(lines) + "\n", tmp_path)

    assert "uv progress noise" not in shown
    assert SKIPPED_MEASUREMENT_LINE in shown
    assert "line 28 returncode > 128 -> returncode >= 128 m.py func/classify_exit_code" in shown
    assert "Time: mutants 0.00s (0)" in shown


@pytest.mark.system
def test_report_filter_still_starts_a_scored_run_at_its_mutation_report(mutate_body, tmp_path):
    log_text = "[1/2] killed line 3\n[2/2] survived line 4\nMutation Report\n===============\nKilled: 1\n"
    shown = _filter(mutate_body, log_text, tmp_path)
    assert shown.splitlines() == ["Mutation Report", "===============", "Killed: 1"]
