"""Every test must carry exactly one of @pytest.mark.{unit,system}
(see pyproject.toml for what each means) as its OWN decorator -- not inherited
from a module- or class-level `pytestmark` default. A default would let a new
test silently satisfy this check without anyone ever deciding its category,
which is the one thing this gate exists to force. The category itself is a
human/model call -- not derived from timing -- but a test that skips the call
entirely is failed here, with its measured duration and a duration-based
suggestion attached to *that* failure, so the fix stays visible right where the
test broke rather than as a separate, easy-to-ignore report."""

import os
from pathlib import Path

import pytest

from ._digest_project import digest_project  # noqa: F401  (pytest fixture, shared by the digest tests)

_CATEGORY_MARKERS = ("unit", "system")
_SYSTEM_THRESHOLD_SECONDS = 0.5

# A system test's nested pytest runs (mutate4py's measurement and executors) load
# only the plugins they name, not every pytest11 entry point in the environment.
# `--no-cov` (neutralising_args) is only valid with pytest-cov loaded, so it is
# named here. Every child reads this variable, worker venvs included, so the
# fixture projects pin pytest-cov in their dependency groups, and a test that
# needs another plugin names it through its own fixture (issue #124, step 6). Set
# per test, so it reaches only the children a system test spawns, never the outer
# run or the unit suite.
_NESTED_PLUGINS = "-p pytest_cov.plugin"


@pytest.fixture(autouse=True)
def _nested_pytest_loads_only_named_plugins(request, monkeypatch):
    if request.node.get_closest_marker("system") is None:
        return
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    existing = os.environ.get("PYTEST_ADDOPTS", "")
    monkeypatch.setenv("PYTEST_ADDOPTS", f"{existing} {_NESTED_PLUGINS}".strip())


@pytest.fixture
def nested_pytest_loads_tach(monkeypatch):
    """For a test whose nested pytest must register tach, the fork-unsafe plugin
    the executor tests exist to detect. Autoload is off, so tach is named here."""
    existing = os.environ.get("PYTEST_ADDOPTS", "")
    monkeypatch.setenv("PYTEST_ADDOPTS", f"{existing} -p tach.pytest_plugin".strip())


# tests/fixtures/** are sample projects other tests spawn as isolated pytest
# subprocesses (e.g. the django_project that test_django_workers_integration.py
# runs) -- they are fixture data, not part of this suite, and were never meant
# to carry a category marker.
_FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    if call.when != "call":
        return
    report = outcome.get_result()
    if report.outcome == "failed":
        return
    try:
        item.path.relative_to(_FIXTURES_DIR)
        return
    except ValueError:
        pass
    category = next((m.name for m in item.own_markers if m.name in _CATEGORY_MARKERS), None)
    if category is not None:
        return
    suggested = "system" if call.duration >= _SYSTEM_THRESHOLD_SECONDS else "unit"
    report.outcome = "failed"
    report.longrepr = (
        f"{item.nodeid} has no @pytest.mark.{{unit,system}} (mandatory -- see "
        "pyproject.toml markers).\n"
        f"Measured duration: {call.duration:.3f}s -> suggested: @pytest.mark.{suggested}\n"
        "(system is a manual call, not duration-based: only for a test that runs real processes "
        "(a fork server, worker servers, nested pytest, a spawned interpreter), outside code mutation and coverage)"
    )
