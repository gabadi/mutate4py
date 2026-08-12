"""Shared precondition for tests that exercise the fork-unsafe-plugin hazard
(mutate4py._forking_executor._FORK_UNSAFE_PLUGIN_MODULES): these tests need
tach.pytest_plugin genuinely loaded in sys.modules to exercise the real
hazard, not a synthetic stand-in. Run with -p no:tach -- or in isolation,
before any other test has imported it -- that precondition doesn't hold, so
these tests must skip rather than fail (issue #70).
"""

import sys

import pytest

__all__ = ["skip_unless_fork_unsafe_plugin_loaded"]

_FORK_UNSAFE_PLUGIN_MODULE = "tach.pytest_plugin"


def skip_unless_fork_unsafe_plugin_loaded() -> None:
    """Skip the calling test if the fork-unsafe plugin under test isn't
    loaded in sys.modules. Call this wherever the bare precondition assert
    used to sit -- including mid-test, after a call expected to load it."""
    if _FORK_UNSAFE_PLUGIN_MODULE not in sys.modules:
        pytest.skip(f"precondition unmet: {_FORK_UNSAFE_PLUGIN_MODULE!r} is not loaded in sys.modules")
