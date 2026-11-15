"""Every test must carry exactly one of @pytest.mark.{unit,system}
(see pyproject.toml for what each means) as its OWN decorator -- not inherited
from a module- or class-level `pytestmark` default. A default would let a new
test silently satisfy this check without anyone ever deciding its category,
which is the one thing this gate exists to force. The category itself is a
human/model call -- not derived from timing -- but a test that skips the call
entirely is failed here, with its measured duration and a duration-based
suggestion attached to *that* failure, so the fix stays visible right where the
test broke rather than as a separate, easy-to-ignore report."""

import multiprocessing.process
import os
import subprocess
import sys
from contextlib import contextmanager
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


# --- Unit tests run in-process (ADR 0030) -----------------------------------
#
# A `unit` test may not create a process. The guard is installed around the test
# call only: fixture setup and teardown are not guarded, and a `system` test is
# not guarded at all. A refusal fails the test and names the call site. A refusal
# the test swallows still fails it, because the hook checks the refusal list once
# the call returns.

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROCESS_ENTRY_POINTS = (
    (subprocess, "Popen", "subprocess.Popen (run, call, check_output)"),
    (os, "fork", "os.fork"),
    (os, "posix_spawn", "os.posix_spawn"),
    (os, "posix_spawnp", "os.posix_spawnp"),
    (multiprocessing.process.BaseProcess, "start", "multiprocessing process start"),
)


def _process_entry_points():
    return [(owner, attr, label) for owner, attr, label in _PROCESS_ENTRY_POINTS if hasattr(owner, attr)]


def _call_site(frame) -> str:
    """The innermost frame, walking out from `frame`, that is this repo's code: not the
    stdlib, not .venv, not this conftest. Falls back to `frame` itself."""
    start = frame
    while frame is not None:
        filename = frame.f_code.co_filename
        if (
            filename != __file__
            and filename.startswith(_REPO_ROOT + os.sep)
            and f"{os.sep}.venv{os.sep}" not in filename
        ):
            return f"{os.path.relpath(filename, _REPO_ROOT)}:{frame.f_lineno} in {frame.f_code.co_name}"
        frame = frame.f_back
    return f"{start.f_code.co_filename}:{start.f_lineno}"


def _refusal(nodeid: str, label: str, refusals: list[str], original):
    def refuse(*_args, **_kwargs):
        site = _call_site(sys._getframe(1))
        message = (
            f"unit test {nodeid} creates a process ({label}) at {site}; mark it `system` or call the code in-process"
        )
        refusals.append(message)
        pytest.fail(message, pytrace=False)

    refuse.guard_original = original
    return refuse


@contextmanager
def _no_process_creation(nodeid: str):
    """Make every process entry point refuse until the block exits, then restore them.

    Yields the refusal list so the caller can fail the test even if the test swallowed the refusal."""
    refusals: list[str] = []
    entry_points = _process_entry_points()
    saved = [(owner, attr, getattr(owner, attr)) for owner, attr, _label in entry_points]
    for (owner, attr, label), (_owner, _attr, original) in zip(entry_points, saved, strict=True):
        setattr(owner, attr, _refusal(nodeid, label, refusals, original))
    try:
        yield refusals
    finally:
        for owner, attr, original in reversed(saved):
            setattr(owner, attr, original)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    if item.get_closest_marker("unit") is None:
        return (yield)
    with _no_process_creation(item.nodeid) as refusals:
        result = yield
    if refusals:
        pytest.fail(refusals[0], pytrace=False)
    return result


def _restore_leaked_refusals():
    """Put the original back on every entry point that still holds a refusal (however deeply nested)."""
    for owner, attr, _label in _process_entry_points():
        current = getattr(owner, attr)
        original = current
        while hasattr(original, "guard_original"):
            original = original.guard_original
        if original is not current:
            setattr(owner, attr, original)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item, nextitem):
    """A test that monkeypatches an entry point during its call makes monkeypatch record the
    refusal as the value to restore. Its teardown runs after the call hook has put the originals
    back, and reinstalls the refusal for the rest of the session. So once teardown is done, put
    the originals back again wherever a refusal remains."""
    try:
        return (yield)
    finally:
        _restore_leaked_refusals()
