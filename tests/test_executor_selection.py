"""Unit tests for executor selection (_executor_selection.py).

Moved from test_run_prep.py (issue 04b): _run_prep.py collapsed once its
_forking_eligible guard was deleted outright (eligibility no longer excludes
a parallel run) and _prepare_executor moved to execution_backends, where
both the single-Worker path and each parallel Worker's own subprocess can
reach it.
"""

import importlib.util
import sys

import pytest

from mutate4py._executor_selection import ForkingOptions, _prepare_executor, select_executor

# This repo's own environment has tach, a fork-unsafe plugin: an in-process
# prime that does not block it gets the subprocess executor.
_NO_TACH = ("-p", "no:tach")


# ── select_executor ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_select_executor_passes_the_no_fork_reason_through_to_the_subprocess_executor(tmp_path):
    chosen = select_executor(
        cwd=str(tmp_path),
        guarded_path=str(tmp_path / "x.py"),
        no_fork_reason="no Mutants selected",
    )
    assert chosen.describe().render() == "subprocess (no Mutants selected)"


@pytest.mark.unit
def test_select_executor_prepares_one_for_a_serial_run(tmp_path):
    from mutate4py._subprocess_executor import SubprocessExecutor

    chosen = select_executor(
        no_fork_reason="--no-fork",
        cwd=str(tmp_path),
        guarded_path=str(tmp_path / "x.py"),
    )
    assert isinstance(chosen, SubprocessExecutor)


# ── _prepare_executor ─────────────────────────────────────────────────────


@pytest.mark.unit
def test_prepare_executor_returns_subprocess_executor_when_not_requested(tmp_path):
    from mutate4py._subprocess_executor import SubprocessExecutor

    executor = _prepare_executor(requested=False, cwd=str(tmp_path), guarded_path=str(tmp_path / "x.py"))
    assert isinstance(executor, SubprocessExecutor)


@pytest.mark.unit
def test_prepare_executor_not_requested_reports_the_no_fork_reason(tmp_path):
    executor = _prepare_executor(requested=False, cwd=str(tmp_path), guarded_path=str(tmp_path / "x.py"))
    assert executor.describe().render() == "subprocess (--no-fork)"


@pytest.mark.unit
def test_prepare_executor_fallback_on_a_non_posix_platform_reports_the_platform(tmp_path, monkeypatch):
    import mutate4py._forking_executor as forking_mod

    monkeypatch.setattr(forking_mod, "is_available", lambda: False)
    executor = _prepare_executor(requested=True, cwd=str(tmp_path), guarded_path=str(tmp_path / "x.py"))
    assert executor.describe().render() == "subprocess (the forking executor needs a POSIX platform)"


@pytest.mark.component
@pytest.mark.skipif(importlib.util.find_spec("tach") is None, reason="needs tach, a fork-unsafe plugin, installed")
def test_prepare_executor_fallback_on_a_fork_unsafe_plugin_names_the_plugin(tmp_path):
    (tmp_path / "conftest.py").write_text("")
    executor = _prepare_executor(requested=True, cwd=str(tmp_path), guarded_path=str(tmp_path / "x.py"))
    assert executor.describe().render() == "subprocess (fork-unsafe plugin: tach.pytest_plugin)"


@pytest.mark.unit
def test_prepare_executor_fallback_on_any_other_unavailability_reports_it_as_unavailable(tmp_path, monkeypatch):
    import mutate4py._forking_executor as forking_mod

    def refuse(self):
        raise forking_mod.ForkingExecutorUnavailable("no pytest here")

    monkeypatch.setattr(forking_mod.ForkingExecutor, "prime", refuse)
    executor = _prepare_executor(requested=True, cwd=str(tmp_path), guarded_path=str(tmp_path / "x.py"))
    assert executor.describe().render() == "subprocess (forking executor unavailable: no pytest here)"


@pytest.mark.unit
def test_prepare_executor_falls_back_to_subprocess_when_platform_unavailable(tmp_path, monkeypatch):
    from mutate4py._subprocess_executor import SubprocessExecutor

    import mutate4py._forking_executor as forking_mod

    monkeypatch.setattr(forking_mod, "is_available", lambda: False)
    executor = _prepare_executor(requested=True, cwd=str(tmp_path), guarded_path=str(tmp_path / "x.py"))
    assert isinstance(executor, SubprocessExecutor)


@pytest.mark.component
def test_prepare_executor_returns_forking_executor_when_requested_and_available(tmp_path):
    from mutate4py._forking_executor import ForkingExecutor

    (tmp_path / "conftest.py").write_text("")
    executor = _prepare_executor(
        requested=True,
        cwd=str(tmp_path),
        guarded_path=str(tmp_path / "not_imported.py"),
        forking=ForkingOptions(prime_args=tuple(_NO_TACH)),
    )
    assert isinstance(executor, ForkingExecutor)


@pytest.mark.component
def test_prepare_executor_forks_for_a_target_already_imported(tmp_path, monkeypatch):
    """A target this process already imported is a harness file, run in a fresh
    interpreter per Mutant: no whole-run fallback to the subprocess executor."""
    import types

    from mutate4py._forking_executor import ForkingExecutor

    (tmp_path / "conftest.py").write_text("")
    target = tmp_path / "imported.py"
    target.write_text("x = 1\n")
    fake_module = types.ModuleType("imported")
    fake_module.__file__ = str(target)
    monkeypatch.setitem(sys.modules, "imported", fake_module)

    executor = _prepare_executor(
        requested=True, cwd=str(tmp_path), guarded_path=str(target), forking=ForkingOptions(prime_args=tuple(_NO_TACH))
    )
    assert isinstance(executor, ForkingExecutor)


@pytest.mark.component
def test_prepare_executor_does_not_import_subprocess_module_when_forking_succeeds(tmp_path, monkeypatch):
    """Self-scanning a leaf module that only the subprocess executor needs
    must keep the forking fast path: when forking succeeds, the subprocess
    executor's module must never be imported."""
    import mutate4py

    monkeypatch.delitem(sys.modules, "mutate4py._subprocess_executor", raising=False)
    monkeypatch.delattr(mutate4py, "_subprocess_executor", raising=False)
    (tmp_path / "conftest.py").write_text("")
    _prepare_executor(
        requested=True,
        cwd=str(tmp_path),
        guarded_path=str(tmp_path / "not_imported.py"),
        forking=ForkingOptions(prime_args=tuple(_NO_TACH)),
    )
    assert "mutate4py._subprocess_executor" not in sys.modules


@pytest.mark.unit
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


class _RecordingServer:
    def __init__(self, **kwargs):
        self.launched_with = kwargs
        self.primed = False

    def prime(self):
        self.primed = True


@pytest.mark.unit
def test_select_executor_primes_a_fork_server_with_the_runs_plugin_blocks_and_ran_at_import_lines(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("mutate4py._worker_protocol.fork_server", lambda **kwargs: _RecordingServer(**kwargs))
    monkeypatch.setattr("mutate4py._forking_executor.is_available", lambda: True)

    chosen = select_executor(
        no_fork_reason=None,
        cwd=str(tmp_path),
        guarded_path=str(tmp_path / "x.py"),
        pytest_args=["-q", "-p", "no:tach", "tests"],
        ran_at_import=frozenset({3}),
    )

    assert chosen.primed
    assert chosen.launched_with == {
        "cwd": str(tmp_path),
        "guarded_path": str(tmp_path / "x.py"),
        "prime_args": ["-p", "no:tach"],
        "ran_at_import": frozenset({3}),
    }


@pytest.mark.unit
def test_select_executor_on_a_platform_without_fork_starts_no_fork_server(tmp_path, monkeypatch):
    def refuse(**kwargs):
        raise AssertionError("a platform without fork must not start a fork server")

    monkeypatch.setattr("mutate4py._worker_protocol.fork_server", refuse)
    monkeypatch.setattr("mutate4py._forking_executor.is_available", lambda: False)

    chosen = select_executor(no_fork_reason=None, cwd=str(tmp_path), guarded_path="x.py")

    assert chosen.describe().render() == "subprocess (the forking executor needs a POSIX platform)"
