"""Collects the pytest node IDs `build_test_context_db` needs, without
running any test body.

`--build-test-contexts` builds a db for every test pytest would run, so it
must discover those node IDs itself first; `pytest --collect-only -q` prints
exactly one line per collected item, in the form `<path>::<name>` (a `::`ed
node ID never occurs in pytest's own status/summary lines), which is how
`_is_node_id_line` tells the two apart.

Every node ID is pinned to `--rootdir=cwd`: pytest otherwise reports node IDs
relative to whatever rootdir it discovers by walking up from cwd looking for
a pyproject.toml/ini file — which differs from cwd whenever cwd isn't itself
that rootdir (e.g. a subdirectory of a larger project). An un-pinned node ID
then can't be re-invoked from that same cwd, which is exactly what
build_test_context_db does per test. Pinning both passes to the same
`--rootdir=cwd` keeps every collected ID a valid, directly re-invokable path.
"""

import os
import subprocess
import sys

__all__ = [
    "TestCollectionError",
    "_collect_argv",
    "collect_pytest_args",
    "collect_test_node_ids",
    "isolated_run_pytest_args",
    "node_ids_from_collect_result",
    "rootdir_pytest_args",
]

_NO_TESTS_COLLECTED_EXIT_CODE = 5


class TestCollectionError(Exception):
    """Raised when pytest collection fails, or collects zero tests."""


def rootdir_pytest_args(cwd: str) -> list[str]:
    """`--rootdir=cwd`, appended last so it wins over any caller-supplied
    --rootdir; see the module docstring for why every pass needs this."""
    return [f"--rootdir={cwd}"]


def isolated_run_pytest_args(pytest_args: list[str], *, cwd: str) -> list[str]:
    """Strip collection-scoping path targets out of pytest_args before it's
    forwarded to a per-test isolated build session.

    --build-test-contexts rejects a positional PATH target, so a path used
    to scope collection (e.g. a subdirectory) can only arrive via
    pytest_args, and collect_test_node_ids needs it there unchanged. But once
    a test has been narrowed to one exact node ID, that same path is
    redundant, and worse: pytest treats a bare path alongside a node ID as an
    ADDITIONAL collection target, so the "isolated" per-test session would
    silently collect and run every test under that path too, instead of just
    the one test the node ID names — defeating build_test_context_db's whole
    per-test isolation guarantee (see docs/adr/0021). Any token that resolves
    to an existing file or directory under cwd is assumed to be such a path
    and dropped; flag tokens (and their values, e.g. `-p no:tach`) are not
    filesystem paths in the ordinary case and pass through unchanged.
    """
    return [arg for arg in pytest_args if not os.path.exists(os.path.join(cwd, arg))]


def _collect_argv(pytest_args: list[str], *, python_executable: str) -> list[str]:
    """Argv for a `--collect-only` pass, scoped by pytest_args (e.g. -k, a path)."""
    return [python_executable, "-m", "pytest", "--collect-only", "-q", *pytest_args]


def _is_node_id_line(line: str) -> bool:
    return "::" in line.strip()


def collect_pytest_args(pytest_args: list[str] | None, *, cwd: str) -> list[str]:
    """The caller's pytest_args with the pinned --rootdir appended; see the
    module docstring for why every collection pass needs that pin."""
    return [*(pytest_args or []), *rootdir_pytest_args(cwd)]


def node_ids_from_collect_result(
    result: subprocess.CompletedProcess[str], *, cwd: str, pytest_args: list[str]
) -> list[str]:
    """Every node ID a finished `--collect-only` pass printed.

    Raises TestCollectionError if the pass itself failed (e.g. a
    collection-time import error) or printed no node ID — an empty result is
    never silently passed through to build_test_context_db, which would
    raise its own less specific "no test node IDs given" error instead. Exit
    5 (`_NO_TESTS_COLLECTED_EXIT_CODE`) is not a failure here: `-q` still
    prints whatever was collected, and the emptiness check below is the one
    that decides.

    cwd and pytest_args name the collection scope in the error messages only.
    """
    if result.returncode not in (0, _NO_TESTS_COLLECTED_EXIT_CODE):
        raise TestCollectionError(
            f"pytest collection failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
        )
    node_ids = [line.strip() for line in result.stdout.splitlines() if _is_node_id_line(line)]
    if not node_ids:
        raise TestCollectionError(f"no tests collected in {cwd!r} with pytest_args={pytest_args!r}")
    return node_ids


def collect_test_node_ids(
    *,
    cwd: str,
    pytest_args: list[str] | None = None,
    python_executable: str = sys.executable,
) -> list[str]:
    """Every node ID `pytest --collect-only` finds, scoped by pytest_args.

    The `--collect-only` subprocess is all this wrapper owns; every decision
    about what came back lives in `node_ids_from_collect_result`.
    """
    scoped_args = collect_pytest_args(pytest_args, cwd=cwd)
    argv = _collect_argv(scoped_args, python_executable=python_executable)
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    return node_ids_from_collect_result(result, cwd=cwd, pytest_args=scoped_args)
