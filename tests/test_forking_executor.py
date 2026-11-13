"""Unit/integration tests for _forking_executor (issue #25 forking executor)."""

import importlib.util
import itertools
import os
import signal
import sys
import textwrap
import time

import pytest

import mutate4py._forking_executor
from mutate4py._forking_executor import (
    ForkingExecutor,
    ForkingExecutorUnavailable,
    ForkUnsafePlugin,
    file_mode,
    fork_unsafe_plugins,
    fresh_interpreter_argv,
    fresh_interpreter_env,
    is_available,
)
from mutate4py._forking_executor import _wait_for_child
from mutate4py._plugin_neutralisation import neutralising_args

# This repo's own environment has tach, a fork-unsafe plugin: an in-process
# prime that does not block it refuses to fork.
_NO_TACH = ["-p", "no:tach"]


# --- is_available ------------------------------------------------------------


@pytest.mark.unit
def test_is_available_true_on_posix():
    assert is_available() is True


@pytest.mark.unit
def test_is_available_false_without_os_fork(monkeypatch):
    monkeypatch.delattr(os, "fork", raising=False)
    assert is_available() is False


# --- file_mode ---------------------------------------------------------------


@pytest.mark.unit
def test_a_file_the_process_loaded_before_prime_is_a_harness_file(tmp_path):
    target = str(tmp_path / "harness.py")
    assert file_mode(target, harness_files={target}, loaded_after_prime={target}) == "harness"


@pytest.mark.unit
def test_a_file_prime_imported_is_loaded(tmp_path):
    target = str(tmp_path / "models.py")
    assert file_mode(target, harness_files=set(), loaded_after_prime={target}) == "loaded"


@pytest.mark.unit
def test_a_file_nothing_imported_is_a_fresh_import(tmp_path):
    target = str(tmp_path / "calc.py")
    other = str(tmp_path / "other.py")
    assert file_mode(target, harness_files={other}, loaded_after_prime={other}) == "fresh import"


@pytest.mark.unit
def test_file_mode_compares_real_paths(tmp_path):
    real = tmp_path / "calc.py"
    real.write_text("")
    link = tmp_path / "link.py"
    link.symlink_to(real)
    assert file_mode(str(link), harness_files=set(), loaded_after_prime={os.path.realpath(real)}) == "loaded"


# --- fork_unsafe_plugins ------------------------------------------------------


@pytest.mark.unit
def test_tach_among_the_registered_plugins_is_fork_unsafe():
    assert fork_unsafe_plugins(["_pytest.python", "tach.pytest_plugin", "pytest_cov.plugin"]) == ["tach.pytest_plugin"]


@pytest.mark.unit
def test_a_session_without_a_known_unsafe_plugin_has_none():
    assert fork_unsafe_plugins(["_pytest.python", "tach"]) == []


@pytest.mark.unit
def test_a_fork_unsafe_plugin_error_names_the_plugin_as_the_whole_reason():
    error = ForkUnsafePlugin(["tach.pytest_plugin", "other.plugin"])
    assert isinstance(error, ForkingExecutorUnavailable)
    assert error.reason == "fork-unsafe plugin: tach.pytest_plugin, other.plugin"


@pytest.mark.unit
def test_any_other_unavailability_is_reported_as_the_forking_executor_unavailable():
    assert ForkingExecutorUnavailable("no pytest").reason == "forking executor unavailable: no pytest"


# --- the fresh-interpreter exec -------------------------------------------------


@pytest.mark.unit
def test_a_fresh_interpreter_runs_this_interpreters_pytest_over_the_args():
    assert fresh_interpreter_argv(["-q", "tests"]) == [sys.executable, "-m", "pytest", "-q", "tests"]


@pytest.mark.unit
def test_a_fresh_interpreter_writes_no_bytecode_and_keeps_the_rest_of_the_environment():
    env = fresh_interpreter_env({"PATH": "/bin", "PYTHONDONTWRITEBYTECODE": ""})
    assert env == {"PATH": "/bin", "PYTHONDONTWRITEBYTECODE": "1"}


# --- ForkingExecutor.prime / run ---------------------------------------------


_module_name_counter = itertools.count()


def _write_fixture_project(tmp_path, *, target_body: str, test_body: str, conftest_body: str = "") -> tuple[str, str]:
    """Write a minimal pytest project; return (cwd, target_path).

    A root conftest.py (even empty) is what makes pytest add the project
    root to sys.path in prepend import mode — the standard flat-layout
    recipe real projects rely on, so the fixture must use it too.

    The target module's name is unique per call (not a fixed "under_test")
    so different tests in this file — all running in one shared outer
    pytest process — cannot collide with each other's sys.modules entries,
    which would otherwise turn a fresh import into a loaded file.
    """
    mod_name = f"under_test_{next(_module_name_counter)}"
    target = tmp_path / f"{mod_name}.py"
    target.write_text(textwrap.dedent(target_body).format(mod=mod_name))
    (tmp_path / "conftest.py").write_text(textwrap.dedent(conftest_body).format(mod=mod_name))
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / f"test_{mod_name}.py").write_text(textwrap.dedent(test_body).format(mod=mod_name))
    return str(tmp_path), str(target)


_ADD_TEST_BODY = "from {mod} import add\ndef test_add():\n    assert add(2, 2) == 4\n"
_ARGS = [*_NO_TACH, "-q", "tests"]


@pytest.mark.component
def test_prime_succeeds_when_target_not_pre_imported(tmp_path):
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=_ADD_TEST_BODY,
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=target, prime_args=_NO_TACH)
    executor.prime()  # must not raise


@pytest.mark.component
def test_prime_and_run_import_from_cwd_without_root_conftest(tmp_path):
    """The console script does not put cwd on sys.path; pytest must still import from it (#82)."""
    n = next(_module_name_counter)
    (tmp_path / f"rootplugin_{n}.py").write_text("")
    (tmp_path / "pytest.ini").write_text(f"[pytest]\naddopts = -p rootplugin_{n}\n")
    target = tmp_path / f"under_test_{n}.py"
    target.write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / f"test_under_test_{n}.py").write_text(
        f"from under_test_{n} import add\n\n\ndef test_add():\n    assert add(2, 2) == 4\n"
    )
    saved = list(sys.path)
    executor = ForkingExecutor(cwd=str(tmp_path), guarded_path=str(target), prime_args=_NO_TACH)
    executor.prime()
    assert executor.run(_ARGS, timeout=30.0) == "survived"
    assert sys.path == saved


@pytest.mark.unit
def test_failed_chdir_does_not_remove_a_preexisting_sys_path_entry(tmp_path, monkeypatch):
    """A cwd that cannot be entered fails before this call touches sys.path, so
    a sys.path entry that was already there must survive the finally block (#82)."""
    missing = str(tmp_path / "does_not_exist")
    monkeypatch.setattr(sys, "path", [*sys.path, missing])
    with pytest.raises(FileNotFoundError):
        mutate4py._forking_executor._run_pytest_output_suppressed(pytest, ["-q"], missing)
    assert missing in sys.path


@pytest.mark.component
def test_prime_neutralises_plugins_on_its_own_collect_only_call(tmp_path, monkeypatch):
    """Regression: prime()'s internal collect-only pytest.main() call is
    itself an in-process, pre-fork pytest re-entry, so it must carry the
    same neutralising_args() as the per-Mutant args in _runner.py — not
    just skip its own reporting. Without this, a target project whose own
    addopts enables a plugin like pytest-cov starts a second Coverage
    instance inside this interpreter during priming, silently corrupting
    this process's own coverage measurement for the rest of the run."""
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=_ADD_TEST_BODY,
    )
    captured_args: list[list[str]] = []
    real_run = mutate4py._forking_executor._run_pytest_output_suppressed

    def spy(pytest_module, args, run_cwd, plugins=()):
        captured_args.append(args)
        return real_run(pytest_module, args, run_cwd, plugins=plugins)

    monkeypatch.setattr(mutate4py._forking_executor, "_run_pytest_output_suppressed", spy)

    executor = ForkingExecutor(cwd=cwd, guarded_path=target, prime_args=_NO_TACH)
    executor.prime()

    assert captured_args, "prime() must invoke pytest.main() via _run_pytest_output_suppressed"
    assert set(neutralising_args()) <= set(captured_args[0])


@pytest.mark.component
def test_run_survives_when_tests_pass(tmp_path):
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=_ADD_TEST_BODY,
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=target, prime_args=_NO_TACH)
    executor.prime()
    status = executor.run(_ARGS, timeout=30.0)
    assert status == "survived"


@pytest.mark.component
def test_run_killed_when_tests_fail(tmp_path):
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a - b\n",  # mutated: - instead of +
        test_body=_ADD_TEST_BODY,
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=target, prime_args=_NO_TACH)
    executor.prime()
    status = executor.run(_ARGS, timeout=30.0)
    assert status == "killed"


@pytest.mark.component
def test_run_reports_no_tests_collected_when_filter_deselects_everything(tmp_path):
    """A -k filter matching nothing is pytest exit 5 ("no tests were
    collected") — must not be scored killed (issue #55), same as the
    subprocess executor (_wait_for_child duplicates run_argv's classification)."""
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=_ADD_TEST_BODY,
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=target, prime_args=_NO_TACH)
    executor.prime()
    status = executor.run([*_ARGS, "-k", "no_such_test_name"], timeout=30.0)
    assert status == "no-tests-collected"


@pytest.mark.component
def test_run_reports_usage_error_for_a_bad_argument(tmp_path):
    """An unrecognized pytest option is exit 4 (usage error) — must not be
    scored killed either (issue #55)."""
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=_ADD_TEST_BODY,
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=target, prime_args=_NO_TACH)
    executor.prime()
    status = executor.run([*_ARGS, "--not-a-real-flag-xyz"], timeout=30.0)
    assert status == "usage-error"


@pytest.mark.component
def test_run_picks_up_post_prime_mutation_from_disk(tmp_path):
    """The central correctness property: priming before the file is mutated
    must not leave a stale pre-mutation module cached for the child."""
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=_ADD_TEST_BODY,
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=target, prime_args=_NO_TACH)
    executor.prime()

    # First mutant: correct code, unmutated -> tests pass -> survived.
    status = executor.run(_ARGS, timeout=30.0)
    assert status == "survived"

    # Apply a mutation on disk, as _run_mutation_loop would between mutants.
    with open(target, "w") as f:
        f.write("def add(a, b):\n    return a - b\n")
    status = executor.run(_ARGS, timeout=30.0)
    assert status == "killed", (
        "child re-used a stale pre-mutation module instead of re-reading the file from disk after fork"
    )

    # Restore and re-run: must go back to survived, proving each fork reads
    # fresh rather than caching the previous child's result.
    with open(target, "w") as f:
        f.write("def add(a, b):\n    return a + b\n")
    status = executor.run(_ARGS, timeout=30.0)
    assert status == "survived"


@pytest.mark.component
def test_run_reports_timeout_and_kills_child(tmp_path):
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=(
            "import time\nfrom {mod} import add\ndef test_add():\n    time.sleep(5)\n    assert add(2, 2) == 4\n"
        ),
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=target, prime_args=_NO_TACH)
    executor.prime()
    status = executor.run(_ARGS, timeout=0.5)
    assert status == "timeout"


@pytest.mark.unit
def test_run_before_prime_raises():
    executor = ForkingExecutor(cwd="/tmp", guarded_path="/tmp/x.py")
    with pytest.raises(ForkingExecutorUnavailable):
        executor.run(["-q"], timeout=1.0)


@pytest.mark.unit
def test_describe_before_any_run_reports_no_fresh_import():
    executor = ForkingExecutor(cwd="/tmp", guarded_path="/tmp/x.py")
    assert executor.describe().render() == "forking (fresh import 0, swap 0, fresh interpreter 0)"


@pytest.mark.component
def test_describe_counts_each_mutant_run_as_a_fresh_import(tmp_path):
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=_ADD_TEST_BODY,
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=target, prime_args=_NO_TACH)
    executor.prime()
    executor.run(_ARGS, timeout=30.0)
    executor.run(_ARGS, timeout=30.0)
    assert executor.describe().render() == "forking (fresh import 2, swap 0, fresh interpreter 0)"


@pytest.mark.component
def test_run_does_not_leak_child_stdout(tmp_path, capsys):
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=(
            "from {mod} import add\ndef test_add():\n    print('SHOULD_NOT_APPEAR')\n    assert add(2, 2) == 4\n"
        ),
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=target, prime_args=_NO_TACH)
    executor.prime()
    executor.run(_ARGS, timeout=30.0)
    captured = capsys.readouterr()
    assert "SHOULD_NOT_APPEAR" not in captured.out
    assert "SHOULD_NOT_APPEAR" not in captured.err


@pytest.mark.component
@pytest.mark.skipif(importlib.util.find_spec("tach") is None, reason="needs tach, a fork-unsafe plugin, installed")
def test_prime_refuses_a_session_that_registers_a_fork_unsafe_plugin(tmp_path):
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=_ADD_TEST_BODY,
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=target)
    with pytest.raises(ForkUnsafePlugin, match="tach.pytest_plugin"):
        executor.prime()


@pytest.mark.component
def test_a_target_the_conftest_imports_runs_in_a_fresh_interpreter_that_reads_the_mutation(tmp_path):
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=_ADD_TEST_BODY,
        conftest_body="import {mod}\n",
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=target, prime_args=_NO_TACH)
    executor.prime()
    assert executor.run(_ARGS, timeout=30.0) == "survived"
    with open(target, "w") as f:
        f.write("def add(a, b):\n    return a - b\n")
    assert executor.run(_ARGS, timeout=30.0) == "killed"
    assert executor.describe().render() == "forking (fresh import 0, swap 0, fresh interpreter 2)"


# --- _wait_for_child ---------------------------------------------------------


@pytest.mark.unit
def test_wait_for_child_reports_killed_when_child_dies_by_signal():
    """A child that dies from an external signal (not its own os._exit, e.g. a
    mutant that crashes the interpreter) must still resolve to "killed", not
    misread WEXITSTATUS on a status word that WIFSIGNALED, not WIFEXITED.

    Not @pytest.mark.integration: the fork()ed child is test scaffolding
    (sleep+exit), not code under test. _wait_for_child, the function this
    test exercises, runs entirely parent-side and is fully visible to
    --cov-context=test.
    """
    pid = os.fork()
    if pid == 0:
        time.sleep(5)
        os._exit(0)  # pragma: no cover - only reached if the signal below fails
    time.sleep(0.05)
    os.kill(pid, signal.SIGTERM)
    status = _wait_for_child(pid, timeout=5.0)
    assert status == "killed"
