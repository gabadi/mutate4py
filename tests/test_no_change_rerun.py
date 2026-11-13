"""No-change rerun (design #89 §5b): a rerun whose code and tests are unchanged since a scored run
skips its Measurement and its Mutants, prints the Survivors the stored Manifest records, writes
nothing, and exits as the scored run did. A changed test file or --mutate-all runs the Mutants again.

Each test drives the real CLI in a throwaway project, so every run is a real scored or skipped run.
"""

import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SKIPPED_LINE = "Measurement: skipped (code and tests unchanged since the last scored run)"
RECORDED_HEADER = "Recorded survivors (not re-run):"

# Every relational mutant of `a > b` is killed by these assertions, so the scored run has no Survivor.
_KILLING_TESTS = (
    "from calc import f\n\n\ndef test_f():\n    assert f(2, 1)\n    assert not f(1, 2)\n    assert not f(1, 1)\n"
)
# `assert f(2, 1)` alone lets `a >= b` and `a != b` survive, so the scored run keeps Survivors.
_SURVIVING_TESTS = "from calc import f\n\n\ndef test_f():\n    assert f(2, 1)\n"
_SRC = "def f(a, b):\n    return a > b\n"


def _run(cwd, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "mutate4py", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env={**os.environ, "PYTHONPATH": os.path.join(REPO_ROOT, "src")},
        timeout=240,
    )


def _project(root, tests: str):
    (root / "tests").mkdir(exist_ok=True)
    (root / "calc.py").write_text(_SRC)
    (root / "tests" / "test_calc.py").write_text(tests)


def _scored(root, *extra: str) -> subprocess.CompletedProcess:
    return _run(str(root), "calc.py", "--pytest-args", "-q tests", *extra)


def _recorded_survivor_lines(stdout: str) -> list[str]:
    """The `  line N desc fid` entries under the Recorded survivors header, if any."""
    lines = stdout.splitlines()
    if RECORDED_HEADER not in lines:
        return []
    start = lines.index(RECORDED_HEADER) + 1
    return [line for line in lines[start:] if line.startswith("  line ")]


@pytest.mark.integration
def test_a_rerun_with_nothing_changed_skips_the_measurement_and_writes_nothing(tmp_path):
    _project(tmp_path, _KILLING_TESTS)
    scored = _scored(tmp_path)
    assert scored.returncode == 0, scored.stdout + scored.stderr
    before = (tmp_path / "calc.py").read_bytes()

    rerun = _scored(tmp_path)

    assert rerun.returncode == 0, rerun.stdout + rerun.stderr
    assert SKIPPED_LINE in rerun.stdout
    assert "Mutation Report" not in rerun.stdout
    assert (tmp_path / "calc.py").read_bytes() == before
    assert not (tmp_path / "calc.py.bak").exists()


@pytest.mark.integration
def test_an_edited_test_file_runs_the_mutants_again(tmp_path):
    _project(tmp_path, _KILLING_TESTS)
    assert _scored(tmp_path).returncode == 0
    (tmp_path / "tests" / "test_calc.py").write_text(_KILLING_TESTS + "\n# edited\n")

    rerun = _scored(tmp_path)

    assert SKIPPED_LINE not in rerun.stdout
    assert "Mutation Report" in rerun.stdout


@pytest.mark.integration
def test_mutate_all_runs_the_mutants_again(tmp_path):
    _project(tmp_path, _KILLING_TESTS)
    assert _scored(tmp_path).returncode == 0

    rerun = _scored(tmp_path, "--mutate-all")

    assert SKIPPED_LINE not in rerun.stdout
    assert "Mutation Report" in rerun.stdout


@pytest.mark.integration
def test_a_skipped_rerun_exits_3_and_lists_the_survivors_the_scored_run_left(tmp_path):
    _project(tmp_path, _SURVIVING_TESTS)
    scored = _scored(tmp_path)
    assert scored.returncode == 3, scored.stdout + scored.stderr
    scored_survivors = [line for line in scored.stdout.splitlines() if line.startswith("  line ")]
    assert scored_survivors

    rerun = _scored(tmp_path)

    assert SKIPPED_LINE in rerun.stdout
    assert rerun.returncode == 3
    assert _recorded_survivor_lines(rerun.stdout)


@pytest.mark.integration
def test_allow_survivors_on_a_skipped_rerun_exits_0_and_still_lists_the_survivors(tmp_path):
    _project(tmp_path, _SURVIVING_TESTS)
    assert _scored(tmp_path).returncode == 3

    rerun = _scored(tmp_path, "--allow-survivors")

    assert SKIPPED_LINE in rerun.stdout
    assert rerun.returncode == 0
    assert _recorded_survivor_lines(rerun.stdout)
