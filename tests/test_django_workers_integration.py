"""Integration tests for issue 05: per-Worker Django test databases.

Real mutate4py CLI subprocess, real Django, real pytest-django, no fakes —
against the reduced fixture project at tests/fixtures/django_project
(excluded from this repo's own pytest collection, see pyproject.toml's
--ignore). Companion to the fake/direct-executor unit tests in
test_worker_server.py and the WorkerProcessExecutor-level round trips in
test_worker_protocol.py, which cover the same mechanism without paying for
a real Django project + CLI dispatch.
"""

import os
import shutil
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FIXTURE_SRC = os.path.join(os.path.dirname(__file__), "fixtures", "django_project")


def _copy_fixture(tmp_path):
    dest = tmp_path / "django_project"
    shutil.copytree(FIXTURE_SRC, dest, ignore=shutil.ignore_patterns("__pycache__", "*.sqlite3*", ".mutate4py"))
    return str(dest)


def _run_cli(cwd: str, extra_args: list[str], *, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": os.path.join(REPO_ROOT, "src")}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "mutate4py", *extra_args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )


# ── two Workers on a Django project: distinct test databases, no collision,
#    verified in the same run as --reuse-db (checklist items 1-3) ────────────


@pytest.mark.system
def test_two_workers_get_distinct_test_databases_with_reuse_db(tmp_path):
    # Premise: a narrowed calc.py Mutant runs only the tests covering its line.
    # tests/test_polls.py::test_calc_thresholds_hold_alongside_a_database_write
    # is the one DB-using test on those lines, so it is what creates the
    # per-Worker test databases asserted below.
    project = _copy_fixture(tmp_path)
    shared_db_dir = tmp_path / "shared_db"
    shared_db_dir.mkdir()

    result = _run_cli(
        project,
        ["calc.py", "--pytest-args=-q --reuse-db", "--max-workers", "2"],
        extra_env={"MUTATE4PY_FIXTURE_DB_DIR": str(shared_db_dir)},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Killed: 2" in result.stdout
    assert "Survived: 0" in result.stdout

    db_files = sorted(shared_db_dir.glob("test_db.sqlite3_*"))
    assert [p.name for p in db_files] == ["test_db.sqlite3_gw1", "test_db.sqlite3_gw2"], (
        "expected one distinct, suffixed test database per Worker; a shared "
        f"unsuffixed test_db.sqlite3 (the pre-fix collision target) is a "
        f"separate, expected baseline-run artifact, not one of these: {db_files}"
    )


# ── an app-loaded module is swapped, its class-body Site runs in a fresh
#    interpreter, and both classify correctly with no whole-run fallback ─────

# This repo's environment has tach, a fork-unsafe plugin: a run that does not
# block it gets the subprocess executor.
_PYTEST_ARGS = "--pytest-args=-p no:tach -q"


@pytest.mark.system
def test_app_loaded_module_swaps_its_method_body_and_runs_its_class_body_site_in_a_fresh_interpreter(tmp_path):
    project = _copy_fixture(tmp_path)
    # The whole file is mutated (no selection flag). Line 11 (votes default) survives: no test pins it,
    # so the run exits 3 unless --allow-survivors accepts it. The assertions below are about the
    # executor modes and the line-14 kill, not about the survivor.
    result = _run_cli(project, ["polls/models.py", "--allow-survivors", _PYTEST_ARGS])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Executor: forking (fresh import 0, swap 1, fresh interpreter 1)" in result.stdout, (
        "polls/models.py is imported by django.setup() during priming: the is_popular body is swapped,"
        " the class-body default runs in a fresh interpreter"
    )
    assert "Killed: 1" in result.stdout
    assert "Survived: 1" in result.stdout


# ── a Mutant in a module outside app loading keeps the warm path
#    (checklist item 6) ───────────────────────────────────────────────────────


@pytest.mark.system
def test_non_app_loaded_module_keeps_warm_path(tmp_path):
    project = _copy_fixture(tmp_path)
    result = _run_cli(project, ["calc.py", _PYTEST_ARGS])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Executor: forking (fresh import 2, swap 0, fresh interpreter 0)" in result.stdout, (
        "calc.py is never imported by django.setup(), so each child imports it fresh"
    )
    assert "Killed: 2" in result.stdout
    assert "Survived: 0" in result.stdout


# ── the primed parent never holds a live DB connection across a fork
#    (checklist item: asserted, not assumed) ──────────────────────────────────

_PROBE_SCRIPT = """
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
import sys
sys.path.insert(0, os.getcwd())

from mutate4py._forking_executor import ForkingExecutor

# django.setup() (which the collect-only prime triggers) imports every
# INSTALLED_APPS model module whichever file is guarded; tach, installed in
# this environment, is fork-unsafe, so the prime blocks it.
target = os.path.join(os.getcwd(), "calc.py")
executor = ForkingExecutor(cwd=os.getcwd(), guarded_path=target, prime_args=["-p", "no:tach"])
executor.prime()

import django  # noqa: E402
from django.db import connections  # noqa: E402

conn = connections["default"]
assert conn.connection is None, "priming must never open a live db connection"
print("PRIME_HELD_NO_DB_CONNECTION")
"""


@pytest.mark.system
def test_primed_parent_never_holds_live_db_connection(tmp_path):
    """Drives ForkingExecutor.prime() directly, in a real subprocess (so
    django.setup() only ever runs once, in a process this test controls) —
    the collect-only priming pass runs django.setup() (app/model import),
    but must never touch the database itself, since a connection opened in
    the parent before a later fork() would be shared/corrupted across
    children rather than reopened per child."""
    project = _copy_fixture(tmp_path)
    result = subprocess.run(
        [sys.executable, "-c", _PROBE_SCRIPT],
        cwd=project,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": os.path.join(REPO_ROOT, "src")},
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PRIME_HELD_NO_DB_CONNECTION" in result.stdout
