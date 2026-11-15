"""Unit tests for the runtime no-process guard in tests/conftest.py (ADR 0030).

They drive the call hook and the patched entry points in-process. Nothing here
creates a process: each probe first checks that its entry point is patched, so an
unpatched call is never made, and every probe names a program that does not exist.
"""

import multiprocessing
import multiprocessing.process
import os
import subprocess

import pytest

from tests import conftest

MISSING = "/nonexistent/mutate4py-guard-probe"

# (owner, attribute, probe). A probe looks its entry point up when it runs, so it
# reaches the patched function, never the real one captured at import time.
ENTRY_POINT_PROBES = (
    (subprocess, "Popen", lambda: subprocess.Popen([MISSING])),
    (os, "fork", lambda: os.fork()),
    (os, "posix_spawn", lambda: os.posix_spawn(MISSING, [MISSING], {})),
    (os, "posix_spawnp", lambda: os.posix_spawnp(MISSING, [MISSING], {})),
    (multiprocessing.process.BaseProcess, "start", lambda: multiprocessing.Process(target=int).start()),
)


class _Item:
    """The two parts of a pytest item that the call hook reads."""

    def __init__(self, nodeid: str, *, unit: bool):
        self.nodeid = nodeid
        self._unit = unit

    def get_closest_marker(self, name: str):
        return object() if self._unit and name == "unit" else None


def _enter(item):
    """Run the call hook for `item` up to the test call. The caller resumes it with next()."""
    gen = conftest.pytest_runtest_call(item)
    next(gen)
    return gen


def _current_entry_points():
    return {(owner, attr): getattr(owner, attr) for owner, attr, _probe in ENTRY_POINT_PROBES}


def _spawn_via_helper():
    """A repo helper that spawns through the stdlib, so the call site is this file, not the stdlib."""
    subprocess.run([MISSING], check=False)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("owner", "attr", "probe"),
    ENTRY_POINT_PROBES,
    ids=["Popen", "fork", "posix_spawn", "posix_spawnp", "multiprocessing-start"],
)
def test_each_process_entry_point_is_refused_during_a_unit_call(owner, attr, probe):
    original = getattr(owner, attr)
    gen = _enter(_Item("tests/example.py::test_example", unit=True))
    try:
        # Identity first: an unpatched probe would run the real call, so stop before it.
        assert getattr(owner, attr) is not original
        with pytest.raises(pytest.fail.Exception, match="creates a process"):
            probe()
    finally:
        with pytest.raises(pytest.fail.Exception):
            next(gen)
    assert getattr(owner, attr) is original


@pytest.mark.unit
def test_refusal_names_the_call_site_the_test_and_the_fix():
    gen = _enter(_Item("tests/example.py::test_names_site", unit=True))
    try:
        with pytest.raises(pytest.fail.Exception) as info:
            _spawn_via_helper()
    finally:
        with pytest.raises(pytest.fail.Exception):
            next(gen)
    message = str(info.value)
    assert "tests/example.py::test_names_site" in message
    assert "tests/test_unit_process_guard.py:" in message
    assert "in _spawn_via_helper" in message
    assert "mark it `system` or call the code in-process" in message


@pytest.mark.unit
def test_a_refusal_the_test_swallows_still_fails_the_test():
    gen = _enter(_Item("tests/example.py::test_swallows", unit=True))
    try:
        try:
            subprocess.Popen([MISSING])
        except BaseException:  # the code under test swallows the refusal
            pass
    finally:
        with pytest.raises(pytest.fail.Exception, match="test_swallows"):
            next(gen)


@pytest.mark.unit
def test_patches_are_restored_when_a_clean_unit_call_finishes():
    before = _current_entry_points()
    gen = _enter(_Item("tests/example.py::test_clean", unit=True))
    with pytest.raises(StopIteration):
        next(gen)
    assert _current_entry_points() == before


@pytest.mark.unit
def test_a_system_test_is_not_guarded():
    before = _current_entry_points()
    gen = conftest.pytest_runtest_call(_Item("tests/example.py::test_real_process", unit=False))
    next(gen)
    assert _current_entry_points() == before
    with pytest.raises(StopIteration):
        next(gen)
