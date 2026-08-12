"""Builds a coverage.py test-context db from isolated per-test sessions.

A single shared `pytest --cov-context=test` session silently attributes a
line touched by several tests to only the first one that reaches it — see
docs/adr/0021-test-context-db-isolated-session-build.md. This module runs
each test in its own `coverage run` process against its own data file, then
merges every file with `coverage combine`, so every covering test survives.
"""

import os
import subprocess
import sys
import tempfile
from typing import Callable

__all__ = [
    "IsolatedSessionRunner",
    "TestContextBuildError",
    "_combine_argv",
    "_run_argv",
    "build_test_context_db",
    "dispatch_isolated_session",
]

IsolatedSessionRunner = Callable[[str, str, list[str]], str]


class TestContextBuildError(Exception):
    """Raised when a per-test coverage session or the final combine fails."""


def _run_argv(node_id: str, *, data_file: str, pytest_args: list[str], python_executable: str) -> list[str]:
    """Argv for one isolated coverage.py session covering exactly node_id."""
    return [
        python_executable,
        "-m",
        "coverage",
        "run",
        f"--context={node_id}",
        f"--data-file={data_file}",
        "-m",
        "pytest",
        node_id,
        *pytest_args,
    ]


def _combine_argv(data_files: list[str], *, output_db_path: str, python_executable: str) -> list[str]:
    """Argv that merges every per-test data file into output_db_path."""
    return [python_executable, "-m", "coverage", "combine", f"--data-file={output_db_path}", *data_files]


def _run_and_check(argv: list[str], *, cwd: str, error_prefix: str) -> None:
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise TestContextBuildError(f"{error_prefix} (exit {result.returncode}):\n{result.stdout}\n{result.stderr}")


def dispatch_isolated_session(
    node_id: str,
    *,
    data_file: str,
    cwd: str,
    pytest_args: list[str],
    isolated_session_runner: IsolatedSessionRunner | None,
) -> None:
    """Run exactly node_id into its own data_file, warm or cold.

    Warm is the injected runner (the forking path); cold is a fresh
    `coverage run -m pytest` subprocess. Either way a session that did not
    complete cleanly raises TestContextBuildError, so the two paths are
    indistinguishable to the caller — see build_test_context_db's docstring.
    """
    if isolated_session_runner is None:
        argv = _run_argv(node_id, data_file=data_file, pytest_args=pytest_args, python_executable=sys.executable)
        _run_and_check(argv, cwd=cwd, error_prefix=f"isolated coverage session for {node_id!r} failed")
        return
    outcome = isolated_session_runner(node_id, data_file, pytest_args)
    if outcome != "survived":
        raise TestContextBuildError(f"isolated coverage session for {node_id!r} did not run cleanly: {outcome}")


def build_test_context_db(
    test_node_ids: list[str],
    *,
    cwd: str,
    output_db_path: str,
    pytest_args: list[str] | None = None,
    isolated_session_runner: IsolatedSessionRunner | None = None,
) -> str:
    """Build a combined test-context db, one isolated coverage.py session per test.

    Each id in test_node_ids runs alone under its own `coverage run` process,
    with a `--context` naming that one test and a `--data-file` no other
    session writes to; `coverage combine` then merges every per-test file
    into output_db_path (resolved against cwd, same as coverage.py itself).
    Slow — one pytest startup per test — by design: see the ADR for why the
    faster single-session `--cov-context=test` alternative silently drops
    every test after the first to touch a shared line.

    If isolated_session_runner is given, it replaces the `coverage run -m
    pytest` subprocess for each node_id (called as
    `runner(node_id, data_file, pytest_args)`, returning the same
    survived/killed/timeout/no-tests-collected/usage-error vocabulary
    Executor.run() uses) — the warm, forking-process path. Anything other
    than "survived" raises TestContextBuildError, same as a nonzero
    subprocess exit would. Left as None, the original cold subprocess path
    runs unchanged.

    Branch vs line coverage mode is whatever the target project's own
    coverage config (pyproject.toml / .coveragerc) already selects; every
    per-test session reads that same config, so all data files combine
    cleanly. Raises TestContextBuildError if test_node_ids is empty, any
    isolated session fails, or the combine step fails.
    """
    if not test_node_ids:
        raise TestContextBuildError("no test node IDs given; nothing to build")
    session_args = list(pytest_args or [])
    with tempfile.TemporaryDirectory(prefix=".mutate4py-test-ctx-") as tmp_dir:
        data_files = []
        for i, node_id in enumerate(test_node_ids):
            data_file = os.path.join(tmp_dir, f".coverage.{i}")
            dispatch_isolated_session(
                node_id,
                data_file=data_file,
                cwd=cwd,
                pytest_args=session_args,
                isolated_session_runner=isolated_session_runner,
            )
            data_files.append(data_file)
        argv = _combine_argv(data_files, output_db_path=output_db_path, python_executable=sys.executable)
        _run_and_check(argv, cwd=cwd, error_prefix="coverage combine failed")
    return output_db_path
