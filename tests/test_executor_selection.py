"""Unit tests for executor selection (_executor_selection.py).

Moved from test_run_prep.py (issue 04b): _run_prep.py collapsed once its
_forking_eligible guard was deleted outright (eligibility no longer excludes
a parallel run) and _prepare_executor moved to execution_backends, where
both the single-Worker path and each parallel Worker's own subprocess can
reach it.
"""

import sys

import pytest

from mutate4py._executor_selection import _prepare_executor

# ── _prepare_executor ─────────────────────────────────────────────────────


def test_prepare_executor_returns_subprocess_executor_when_not_requested(tmp_path):
    from mutate4py._subprocess_executor import SubprocessExecutor

    executor = _prepare_executor(requested=False, cwd=str(tmp_path), guarded_path=str(tmp_path / "x.py"))
    assert isinstance(executor, SubprocessExecutor)


def test_prepare_executor_falls_back_to_subprocess_when_platform_unavailable(tmp_path, monkeypatch):
    from mutate4py._subprocess_executor import SubprocessExecutor

    import mutate4py._forking_executor as forking_mod

    monkeypatch.setattr(forking_mod, "is_available", lambda: False)
    executor = _prepare_executor(requested=True, cwd=str(tmp_path), guarded_path=str(tmp_path / "x.py"))
    assert isinstance(executor, SubprocessExecutor)


@pytest.mark.integration
def test_prepare_executor_returns_forking_executor_when_requested_and_available(tmp_path):
    from mutate4py._forking_executor import ForkingExecutor

    (tmp_path / "conftest.py").write_text("")
    executor = _prepare_executor(requested=True, cwd=str(tmp_path), guarded_path=str(tmp_path / "not_imported.py"))
    assert isinstance(executor, ForkingExecutor)


@pytest.mark.integration
def test_prepare_executor_falls_back_when_target_already_leaked(tmp_path, monkeypatch):
    """A module-leak during priming must fall back to the subprocess
    executor rather than propagate."""
    import types

    from mutate4py._subprocess_executor import SubprocessExecutor

    (tmp_path / "conftest.py").write_text("")
    target = tmp_path / "leaked.py"
    target.write_text("x = 1\n")
    fake_module = types.ModuleType("leaked")
    fake_module.__file__ = str(target)
    monkeypatch.setitem(sys.modules, "leaked", fake_module)

    executor = _prepare_executor(requested=True, cwd=str(tmp_path), guarded_path=str(target))
    assert isinstance(executor, SubprocessExecutor)


@pytest.mark.integration
def test_prepare_executor_does_not_import_subprocess_module_when_forking_succeeds(tmp_path, monkeypatch):
    """Self-scanning a leaf module that only the subprocess executor needs
    must keep the forking fast path: when forking succeeds, the subprocess
    executor's module must never be imported."""
    import mutate4py

    monkeypatch.delitem(sys.modules, "mutate4py._subprocess_executor", raising=False)
    monkeypatch.delattr(mutate4py, "_subprocess_executor", raising=False)
    (tmp_path / "conftest.py").write_text("")
    _prepare_executor(requested=True, cwd=str(tmp_path), guarded_path=str(tmp_path / "not_imported.py"))
    assert "mutate4py._subprocess_executor" not in sys.modules


def test_prepare_executor_imports_subprocess_module_when_falling_back(tmp_path, monkeypatch):
    import mutate4py

    # The parent package caches its submodule as an attribute on import,
    # independent of sys.modules; deleting only the sys.modules entry would
    # leave that attribute pointing at whatever this test re-imports,
    # desyncing later `import mutate4py._subprocess_executor as x` lookups
    # (which resolve through the package attribute, not sys.modules) from
    # the module every other test already holds a reference to.
    monkeypatch.delitem(sys.modules, "mutate4py._subprocess_executor", raising=False)
    monkeypatch.delattr(mutate4py, "_subprocess_executor", raising=False)
    _prepare_executor(requested=False, cwd=str(tmp_path), guarded_path=str(tmp_path / "x.py"))
    assert "mutate4py._subprocess_executor" in sys.modules
