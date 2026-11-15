"""A scored run with pytest's plugin autoload off (#127).

`--no-cov` is a pytest usage error unless pytest-cov is loaded in the pytest that receives it.
With PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest-cov loads only when the run names it with `-p`.
mutate4py used to add `--no-cov` whenever pytest_cov was importable in its own process, so such a
run exited 4 with "unrecognized arguments: --no-cov" (ADR 0020, amended).

Each test drives the real CLI in a throwaway project. The environment is built from the helpers the
other nested-pytest tests use (acceptance/steps/nested_pytest_helpers.py), with PYTEST_ADDOPTS cleared
so that the only thing that can load pytest-cov is what the test names.
"""

import os
import subprocess
import sys

import pytest

from acceptance.steps.nested_pytest_helpers import ADDOPTS, AUTOLOAD_SWITCH, nested_pytest_env

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Every relational mutant of `a > b` is killed by these assertions, so the scored run has no Survivor.
_SRC = "def f(a, b):\n    return a > b\n"
_TESTS = "from calc import f\n\n\ndef test_f():\n    assert f(2, 1)\n    assert not f(1, 2)\n    assert not f(1, 1)\n"


def _scored(root, pytest_args: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    (root / "tests").mkdir()
    (root / "calc.py").write_text(_SRC)
    (root / "tests" / "test_calc.py").write_text(_TESTS)
    return subprocess.run(
        [sys.executable, "-m", "mutate4py", "calc.py", "--pytest-args", pytest_args],
        capture_output=True,
        text=True,
        cwd=root,
        env={**env, "PYTHONPATH": os.path.join(REPO_ROOT, "src")},
        timeout=240,
    )


def _autoload_off_env() -> dict[str, str]:
    return {**os.environ, AUTOLOAD_SWITCH: "1", ADDOPTS: ""}


@pytest.mark.system
def test_a_run_with_autoload_off_and_no_pytest_cov_scores_normally(tmp_path):
    run = _scored(tmp_path, "-q tests", _autoload_off_env())

    assert run.returncode == 0, run.stdout + run.stderr
    assert "unrecognized arguments" not in run.stdout + run.stderr
    assert "Mutation Report" in run.stdout


@pytest.mark.system
def test_a_run_with_autoload_off_that_names_pytest_cov_in_its_pytest_args_scores_normally(tmp_path):
    run = _scored(tmp_path, "-q -p pytest_cov tests", _autoload_off_env())

    assert run.returncode == 0, run.stdout + run.stderr
    assert "Mutation Report" in run.stdout


@pytest.mark.system
def test_a_run_with_autoload_on_scores_normally_with_no_cov(tmp_path):
    run = _scored(tmp_path, "-q tests", nested_pytest_env(os.environ, autoload=True))

    assert run.returncode == 0, run.stdout + run.stderr
    assert "Mutation Report" in run.stdout
