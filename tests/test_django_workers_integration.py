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


def _write_lcov(path: str, covered_lines: list[int]) -> str:
    da = "\n".join(f"DA:{ln},1" for ln in covered_lines)
    lcov_path = os.path.join(os.path.dirname(path), "coverage.lcov")
    with open(lcov_path, "w") as f:
        f.write(f"SF:{path}\n{da}\nend_of_record\n")
    return lcov_path


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


@pytest.mark.integration
def test_two_workers_get_distinct_test_databases_with_reuse_db(tmp_path):
    project = _copy_fixture(tmp_path)
    lcov = _write_lcov(os.path.join(project, "calc.py"), [6, 10])
    shared_db_dir = tmp_path / "shared_db"
    shared_db_dir.mkdir()

    result = _run_cli(
        project,
        ["calc.py", "--mutate-all", "--pytest-args=-q --reuse-db", "--lcov", lcov, "--max-workers", "2"],
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


# ── a Mutant in an app-loaded module degrades but is still killed correctly
#    (checklist item 5) ───────────────────────────────────────────────────────


@pytest.mark.integration
def test_app_loaded_module_degrades_to_subprocess_and_is_killed(tmp_path):
    project = _copy_fixture(tmp_path)
    lcov = _write_lcov(os.path.join(project, "polls", "models.py"), [14])

    result = _run_cli(project, ["polls/models.py", "--mutate-all", "--pytest-args=-q", "--lcov", lcov])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "forking executor unavailable" in result.stdout, (
        "polls/models.py is imported by django.setup() during priming, so the "
        "module-leak guard must force the subprocess executor"
    )
    assert "Killed: 1" in result.stdout
    assert "Survived: 0" in result.stdout


# ── a Mutant in a module outside app loading keeps the warm path
#    (checklist item 6) ───────────────────────────────────────────────────────


@pytest.mark.integration
def test_non_app_loaded_module_keeps_warm_path(tmp_path):
    project = _copy_fixture(tmp_path)
    lcov = _write_lcov(os.path.join(project, "calc.py"), [6])

    result = _run_cli(project, ["calc.py", "--mutate-all", "--pytest-args=-q", "--lcov", lcov])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "forking executor unavailable" not in result.stdout, (
        "calc.py is never imported by django.setup(), so the forking executor must stay primed rather than degrading"
    )
    assert "Killed: 1" in result.stdout
    assert "Survived: 0" in result.stdout


# ── the primed parent never holds a live DB connection across a fork
#    (checklist item: asserted, not assumed) ──────────────────────────────────

_PROBE_SCRIPT = """
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
import sys
sys.path.insert(0, os.getcwd())

from mutate4py._forking_executor import ForkingExecutor

# calc.py, not polls/models.py: django.setup() (which the collect-only
# prime triggers) imports every INSTALLED_APPS model module regardless of
# which file is guarded, so priming would trip the (separately tested)
# module-leak guard for an app-loaded guarded_path before this assertion
# ever ran. calc.py isn't app-loaded, so priming here succeeds and this
# test actually exercises the db-connection invariant.
target = os.path.join(os.getcwd(), "calc.py")
executor = ForkingExecutor(cwd=os.getcwd(), guarded_path=target)
executor.prime()

import django  # noqa: E402
from django.db import connections  # noqa: E402

conn = connections["default"]
assert conn.connection is None, "priming must never open a live db connection"
print("PRIME_HELD_NO_DB_CONNECTION")
"""


@pytest.mark.integration
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
