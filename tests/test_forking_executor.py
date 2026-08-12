"""Unit/integration tests for _forking_executor (issue #25 forking executor)."""

import itertools
import os
import signal
import sys
import textwrap
import time
import types

import coverage
import pytest

import mutate4py._forking_executor
from mutate4py._forking_executor import (
    ForkingExecutor,
    ForkingExecutorUnavailable,
    ModuleLeakError,
    assert_source_clean,
    is_available,
    isolated_coverage_session_safe,
)
from mutate4py._forking_executor import _wait_for_child
from mutate4py._plugin_neutralisation import neutralising_args
from mutate4py._test_selection import TestContextDB

from ._fork_unsafe_plugin_helpers import skip_unless_fork_unsafe_plugin_loaded


# --- is_available ------------------------------------------------------------


@pytest.mark.unit
def test_is_available_true_on_posix():
    assert is_available() is True


@pytest.mark.unit
def test_is_available_false_without_os_fork(monkeypatch):
    monkeypatch.delattr(os, "fork", raising=False)
    assert is_available() is False


# --- assert_source_clean / _leaked_modules ----------------------------------


@pytest.mark.unit
def test_assert_source_clean_passes_when_target_not_imported(tmp_path):
    target = tmp_path / "not_imported.py"
    target.write_text("x = 1\n")
    assert_source_clean(str(target))


@pytest.mark.unit
def test_assert_source_clean_raises_when_target_already_imported(tmp_path, monkeypatch):
    target = tmp_path / "leaked_target.py"
    target.write_text("x = 1\n")
    fake_module = types.ModuleType("leaked_target")
    fake_module.__file__ = str(target)
    monkeypatch.setitem(sys.modules, "leaked_target", fake_module)
    with pytest.raises(ModuleLeakError, match="leaked_target"):
        assert_source_clean(str(target))


@pytest.mark.unit
def test_assert_source_clean_ignores_modules_without_file(monkeypatch, tmp_path):
    target = tmp_path / "no_file_module.py"
    target.write_text("x = 1\n")
    fake_module = types.ModuleType("builtin_like")
    monkeypatch.setitem(sys.modules, "builtin_like", fake_module)
    assert_source_clean(str(target))


@pytest.mark.unit
def test_assert_source_clean_ignores_unrelated_modules(tmp_path):
    unrelated = tmp_path / "unrelated.py"
    unrelated.write_text("x = 1\n")
    target = tmp_path / "target.py"
    target.write_text("x = 1\n")
    # `os` itself is always in sys.modules; unrelated to target, must not trip.
    assert_source_clean(str(target))


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
    which would otherwise mask exactly the leak this module exists to catch.
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
_ARGS = ["-q", "tests"]


@pytest.mark.integration
def test_prime_succeeds_when_target_not_pre_imported(tmp_path):
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=_ADD_TEST_BODY,
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=target)
    executor.prime()  # must not raise


@pytest.mark.integration
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

    def spy(pytest_module, args, run_cwd):
        captured_args.append(args)
        return real_run(pytest_module, args, run_cwd)

    monkeypatch.setattr(mutate4py._forking_executor, "_run_pytest_output_suppressed", spy)

    executor = ForkingExecutor(cwd=cwd, guarded_path=target)
    executor.prime()

    assert captured_args, "prime() must invoke pytest.main() via _run_pytest_output_suppressed"
    assert set(neutralising_args()) <= set(captured_args[0])


@pytest.mark.integration
def test_prime_raises_module_leak_when_conftest_imports_target(tmp_path):
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=_ADD_TEST_BODY,
        conftest_body="import {mod}\n",
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=target)
    with pytest.raises(ModuleLeakError):
        executor.prime()


@pytest.mark.integration
def test_prime_leak_does_not_poison_a_later_same_named_file(tmp_path):
    """Regression: a leaked module from one file's prime() must not survive
    to fool a *different* file's leak check later in the same process —
    exactly the shape of a directory batch run with colliding basenames."""
    dir_a = tmp_path / "a"
    dir_a.mkdir()
    cwd_a, target_a = _write_fixture_project(
        dir_a,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=_ADD_TEST_BODY,
        conftest_body="import {mod}\n",
    )
    executor_a = ForkingExecutor(cwd=cwd_a, guarded_path=target_a)
    with pytest.raises(ModuleLeakError):
        executor_a.prime()

    # A second, unrelated file that happens to reuse the same module name.
    mod_name = os.path.splitext(os.path.basename(target_a))[0]
    dir_b = tmp_path / "b"
    dir_b.mkdir()
    target_b = dir_b / f"{mod_name}.py"
    target_b.write_text("def add(a, b):\n    return a + b\n")
    (dir_b / "conftest.py").write_text("")
    tests_b = dir_b / "tests"
    tests_b.mkdir()
    (tests_b / f"test_{mod_name}.py").write_text(_ADD_TEST_BODY.format(mod=mod_name))

    executor_b = ForkingExecutor(cwd=str(dir_b), guarded_path=str(target_b))
    executor_b.prime()  # must not raise: file a's leak must not have persisted


@pytest.mark.integration
def test_run_survives_when_tests_pass(tmp_path):
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=_ADD_TEST_BODY,
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=target)
    executor.prime()
    status = executor.run(_ARGS, timeout=30.0)
    assert status == "survived"


@pytest.mark.integration
def test_run_killed_when_tests_fail(tmp_path):
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a - b\n",  # mutated: - instead of +
        test_body=_ADD_TEST_BODY,
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=target)
    executor.prime()
    status = executor.run(_ARGS, timeout=30.0)
    assert status == "killed"


@pytest.mark.integration
def test_run_reports_no_tests_collected_when_filter_deselects_everything(tmp_path):
    """A -k filter matching nothing is pytest exit 5 ("no tests were
    collected") — must not be scored killed (issue #55), same as the
    subprocess executor (_wait_for_child duplicates run_argv's classification)."""
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=_ADD_TEST_BODY,
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=target)
    executor.prime()
    status = executor.run(["-q", "tests", "-k", "no_such_test_name"], timeout=30.0)
    assert status == "no-tests-collected"


@pytest.mark.integration
def test_run_reports_usage_error_for_a_bad_argument(tmp_path):
    """An unrecognized pytest option is exit 4 (usage error) — must not be
    scored killed either (issue #55)."""
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=_ADD_TEST_BODY,
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=target)
    executor.prime()
    status = executor.run(["-q", "tests", "--not-a-real-flag-xyz"], timeout=30.0)
    assert status == "usage-error"


@pytest.mark.integration
def test_run_picks_up_post_prime_mutation_from_disk(tmp_path):
    """The central correctness property: priming before the file is mutated
    must not leave a stale pre-mutation module cached for the child."""
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=_ADD_TEST_BODY,
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=target)
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


@pytest.mark.integration
def test_run_reports_timeout_and_kills_child(tmp_path):
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=(
            "import time\nfrom {mod} import add\ndef test_add():\n    time.sleep(5)\n    assert add(2, 2) == 4\n"
        ),
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=target)
    executor.prime()
    status = executor.run(_ARGS, timeout=0.5)
    assert status == "timeout"


def test_run_before_prime_raises():
    executor = ForkingExecutor(cwd="/tmp", guarded_path="/tmp/x.py")
    with pytest.raises(ForkingExecutorUnavailable):
        executor.run(["-q"], timeout=1.0)


@pytest.mark.integration
def test_run_does_not_leak_child_stdout(tmp_path, capsys):
    cwd, target = _write_fixture_project(
        tmp_path,
        target_body="def add(a, b):\n    return a + b\n",
        test_body=(
            "from {mod} import add\ndef test_add():\n    print('SHOULD_NOT_APPEAR')\n    assert add(2, 2) == 4\n"
        ),
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=target)
    executor.prime()
    executor.run(_ARGS, timeout=30.0)
    captured = capsys.readouterr()
    assert "SHOULD_NOT_APPEAR" not in captured.out
    assert "SHOULD_NOT_APPEAR" not in captured.err


# --- isolated_coverage_session_safe -------------------------------------------


@pytest.mark.unit
def test_isolated_coverage_session_safe_false_when_a_known_unsafe_plugin_is_loaded(monkeypatch):
    """Regression for the acceptance-suite hang this precheck exists to
    prevent: tach.pytest_plugin is genuinely loaded in this test process
    (it's this repo's own pytest plugin), so this assertion also proves the
    check fires for real, not just against a synthetic fake module."""
    skip_unless_fork_unsafe_plugin_loaded()
    assert isolated_coverage_session_safe() is False


@pytest.mark.unit
def test_isolated_coverage_session_safe_true_when_no_unsafe_plugin_is_loaded(monkeypatch):
    monkeypatch.delitem(sys.modules, "tach.pytest_plugin", raising=False)
    assert isolated_coverage_session_safe() is True


# --- ForkingExecutor.run_isolated_coverage_session ---------------------------


def _write_coverage_fixture_project(tmp_path) -> str:
    """Write a minimal two-test project with a line shared by both tests plus
    one line private to each, mirroring tests/fixtures/overlapping_coverage/
    but built fresh under tmp_path (real system tmp, outside this repo).

    Must NOT reuse the in-repo fixture: priming followed by a second
    in-process pytest.main() call inside this repo's own tree deadlocks
    under pytest-tach's native fork-time lock (issue #51 spike finding);
    tmp_path sidesteps the plugin's config discovery entirely. branch=True
    in .coveragerc routes context lookups through the arc table, avoiding
    the unrelated, separately-tracked off-by-one in the line-only numbits
    decoder (mutate4py._test_selection._numbits_to_lines).
    """
    (tmp_path / ".coveragerc").write_text("[run]\nbranch = True\n")
    (tmp_path / "shared.py").write_text(
        "def shared():\n    return 1\n\n\ndef only_a():\n    return 'a'\n\n\ndef only_b():\n    return 'b'\n"
    )
    (tmp_path / "test_a.py").write_text(
        "from shared import only_a, shared\n\n\ndef test_from_a():\n    assert shared() == 1\n"
        "    assert only_a() == 'a'\n"
    )
    (tmp_path / "test_b.py").write_text(
        "from shared import only_b, shared\n\n\ndef test_from_b():\n    assert shared() == 1\n"
        "    assert only_b() == 'b'\n"
    )
    return str(tmp_path)


_SHARED_LINE = 2
_ONLY_A_LINE = 6
_ONLY_B_LINE = 10


@pytest.mark.integration
def test_run_isolated_coverage_session_narrows_shared_line_to_both_tests(tmp_path, monkeypatch):
    """Central correctness property (ADR 0021): two isolated per-test
    sessions, combined, must narrow a shared line to both covering tests and
    a private line to only its own test. This also exercises the
    chdir-before-Coverage()-construction ordering fix -- the outer pytest
    process's own cwd is this repo's root (source=["mutate4py"] in
    pyproject.toml), so a regressed ordering would silently record zero data
    for this fixture project's files instead of raising.

    isolated_coverage_session_safe stubbed True: this dev venv's own
    tach.pytest_plugin is reloaded by prime()'s internal collect-only
    pytest.main() call regardless of cwd (confirmed empirically -- it is not
    specific to being inside this repo's tree), so the real gate would
    always refuse here. That gate has its own dedicated tests above; this
    test isolates the fork/coverage mechanics it protects."""
    monkeypatch.setattr(mutate4py._forking_executor, "isolated_coverage_session_safe", lambda: True)
    cwd = _write_coverage_fixture_project(tmp_path)
    executor = ForkingExecutor(cwd=cwd, guarded_path=cwd)
    executor.prime()

    data_a = str(tmp_path / ".coverage.a")
    data_b = str(tmp_path / ".coverage.b")
    status_a = executor.run_isolated_coverage_session(
        "test_a.py::test_from_a", data_file=data_a, pytest_args=["-q"], timeout=30.0
    )
    status_b = executor.run_isolated_coverage_session(
        "test_b.py::test_from_b", data_file=data_b, pytest_args=["-q"], timeout=30.0
    )
    assert status_a == "survived"
    assert status_b == "survived"

    combined_path = str(tmp_path / "combined.coverage")
    combined = coverage.Coverage(data_file=combined_path)
    combined.combine(data_paths=[data_a, data_b], strict=True)
    combined.save()

    db = TestContextDB(combined_path)
    try:
        shared_py = str(tmp_path / "shared.py")
        node_ids = sorted(["test_a.py::test_from_a", "test_b.py::test_from_b"])
        assert db.tests_for_line(shared_py, _SHARED_LINE) == ("narrowed", node_ids)
        assert db.tests_for_line(shared_py, _ONLY_A_LINE) == ("narrowed", ["test_a.py::test_from_a"])
        assert db.tests_for_line(shared_py, _ONLY_B_LINE) == ("narrowed", ["test_b.py::test_from_b"])
    finally:
        db.close()


@pytest.mark.integration
def test_run_isolated_coverage_session_killed_when_test_fails(tmp_path, monkeypatch):
    """isolated_coverage_session_safe stubbed True: see the docstring on
    test_run_isolated_coverage_session_narrows_shared_line_to_both_tests."""
    monkeypatch.setattr(mutate4py._forking_executor, "isolated_coverage_session_safe", lambda: True)
    cwd = _write_coverage_fixture_project(tmp_path)
    (tmp_path / "test_a.py").write_text(
        "from shared import shared\n\n\ndef test_from_a():\n    assert shared() == 999\n"
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=cwd)
    executor.prime()
    status = executor.run_isolated_coverage_session(
        "test_a.py::test_from_a", data_file=str(tmp_path / ".coverage.a"), pytest_args=["-q"], timeout=30.0
    )
    assert status == "killed"


@pytest.mark.integration
def test_run_isolated_coverage_session_reports_timeout_and_kills_child(tmp_path, monkeypatch):
    """isolated_coverage_session_safe stubbed True: see the docstring on
    test_run_isolated_coverage_session_narrows_shared_line_to_both_tests."""
    monkeypatch.setattr(mutate4py._forking_executor, "isolated_coverage_session_safe", lambda: True)
    cwd = _write_coverage_fixture_project(tmp_path)
    (tmp_path / "test_a.py").write_text(
        "import time\nfrom shared import shared\n\n\ndef test_from_a():\n    time.sleep(5)\n    assert shared() == 1\n"
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=cwd)
    executor.prime()
    status = executor.run_isolated_coverage_session(
        "test_a.py::test_from_a", data_file=str(tmp_path / ".coverage.a"), pytest_args=["-q"], timeout=0.5
    )
    assert status == "timeout"


@pytest.mark.integration
def test_run_isolated_coverage_session_before_prime_raises(tmp_path):
    executor = ForkingExecutor(cwd=str(tmp_path), guarded_path=str(tmp_path))
    with pytest.raises(ForkingExecutorUnavailable):
        executor.run_isolated_coverage_session(
            "test_a.py::test_from_a", data_file=str(tmp_path / ".coverage.a"), pytest_args=[], timeout=1.0
        )


@pytest.mark.integration
def test_run_isolated_coverage_session_raises_when_a_fork_unsafe_plugin_is_loaded_after_prime(tmp_path):
    """Self-enforcement regression (issue #51 Standards review): a fork-unsafe
    plugin (e.g. tach.pytest_plugin) can get loaded into sys.modules by
    prime()'s own internal pytest.main() call, not just by whatever loaded
    the interpreter -- verified for real here, since this dev venv's tach
    plugin does exactly that (see the empirical note on
    test_run_isolated_coverage_session_narrows_shared_line_to_both_tests).
    run_isolated_coverage_session must refuse on its own, not rely on a
    caller (e.g. _dispatch.py) to have checked isolated_coverage_session_safe()
    beforehand -- a direct caller that skips that check must still be
    protected from the fork-after-prime deadlock hazard."""
    cwd = _write_coverage_fixture_project(tmp_path)
    executor = ForkingExecutor(cwd=cwd, guarded_path=cwd)
    executor.prime()
    skip_unless_fork_unsafe_plugin_loaded()
    with pytest.raises(ForkingExecutorUnavailable):
        executor.run_isolated_coverage_session(
            "test_a.py::test_from_a", data_file=str(tmp_path / ".coverage.a"), pytest_args=["-q"], timeout=30.0
        )


@pytest.mark.integration
def test_run_isolated_coverage_session_does_not_leak_child_stdout(tmp_path, capsys, monkeypatch):
    """isolated_coverage_session_safe stubbed True: see the docstring on
    test_run_isolated_coverage_session_narrows_shared_line_to_both_tests."""
    monkeypatch.setattr(mutate4py._forking_executor, "isolated_coverage_session_safe", lambda: True)
    cwd = _write_coverage_fixture_project(tmp_path)
    (tmp_path / "test_a.py").write_text(
        "from shared import shared\n\n\ndef test_from_a():\n    print('SHOULD_NOT_APPEAR')\n    assert shared() == 1\n"
    )
    executor = ForkingExecutor(cwd=cwd, guarded_path=cwd)
    executor.prime()
    executor.run_isolated_coverage_session(
        "test_a.py::test_from_a", data_file=str(tmp_path / ".coverage.a"), pytest_args=["-q"], timeout=30.0
    )
    captured = capsys.readouterr()
    assert "SHOULD_NOT_APPEAR" not in captured.out
    assert "SHOULD_NOT_APPEAR" not in captured.err


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
