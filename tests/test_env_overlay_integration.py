"""Integration regression for the `uv run --with` overlay (ADR 0025): the
command the foreign-interpreter guard recommends must be accepted in a project
that has its own `.venv`.

Real CLI, real `uv run`, no fakes. The project is a copy of the plain pytest
fixture (no Django: the guard is what is under test), which declares a pytest
dev group, so `uv run` syncs the project's own `.venv` with pytest in it before
mutate4py starts.
"""

import os
import shutil
import subprocess

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FIXTURE_SRC = os.path.join(os.path.dirname(__file__), "fixtures", "plain_project")


def _copy_fixture(tmp_path):
    dest = tmp_path / "plain_project"
    shutil.copytree(FIXTURE_SRC, dest, ignore=shutil.ignore_patterns("__pycache__", ".mutate4py"))
    return str(dest)


def _write_coverage(project: str) -> None:
    """Pre-generated LCOV at the default location (project root), so the run
    gets past its coverage-input check; the lines are the ones the plain tests
    cover in calc.py."""
    calc = os.path.join(project, "calc.py")
    da = "\n".join(f"DA:{line},1" for line in (6, 10))
    with open(os.path.join(project, "coverage.lcov"), "w") as f:
        f.write(f"SF:{calc}\n{da}\nend_of_record\n")


@pytest.mark.integration
@pytest.mark.parametrize("extra_args", [[], ["--max-workers", "2"]], ids=["serial", "max-workers-2"])
def test_uv_run_with_repo_root_is_accepted_in_project_with_its_own_venv(tmp_path, extra_args):
    project = _copy_fixture(tmp_path)
    _write_coverage(project)
    # --with-editable: still a `uv run` overlay on the project, but uv installs
    # the repo root as an editable, so the run reads src/ as it is on disk. A
    # plain `--with <dir>` build is cached keyed on pyproject.toml and can serve
    # a stale copy of src/ after an edit; --reinstall-package mutate4py did not
    # force a rebuild in a scratch copy, so it is not a fix.
    command = [
        "uv",
        "run",
        "--with-editable",
        REPO_ROOT,
        "mutate4py",
        "calc.py",
        "--mutate-all",
        "--allow-survivors",
        *extra_args,
    ]
    env = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
    result = subprocess.run(command, cwd=project, capture_output=True, text=True, env=env, timeout=600)
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
