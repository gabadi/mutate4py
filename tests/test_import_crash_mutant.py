"""A Mutant that breaks the module at import is killed, on every Executor (ADR 0018).

The conftest imports the module under test. A Mutant that raises at import fails that import, so
pytest exits 4 ("ImportError while loading conftest") before it runs a test. The Mutant caused
that exit: the same argv runs tests on the original code. These tests run real Measurements and real
Executors, on the forking executor and on `--no-fork`, and pin that the Mutant is killed and the run
goes on. A pytest argv that is itself bad must still abort the run, on both Executors.
"""

import os
import re

import pytest

from ._measurement_helpers import measurement_for, record_for
from ._pytest_project_helpers import write_import_time_lookup_project
from mutate4py._manifest import strip_manifest
from mutate4py._runner import RunMutationsRequest, run_mutations

_ARGS = ["-p", "no:tach", "-q", "tests"]
_EXECUTORS = pytest.mark.parametrize(
    "forking_requested, executor_line",
    [(True, "Executor: forking ("), (False, "Executor: subprocess (--no-fork)")],
    ids=["forking", "no-fork"],
)
_BOTH_EXECUTORS = pytest.mark.parametrize("forking_requested", [True, False], ids=["forking", "no-fork"])


def _source_on_disk(path) -> str:
    """The guarded file's text without the Manifest footer a finished run embeds."""
    with open(path) as f:
        return strip_manifest(f.read()).rstrip("\n") + "\n"


def _request(root, source, **extra) -> RunMutationsRequest:
    return RunMutationsRequest(
        path=str(root / "calc.py"),
        source=source,
        pytest_args=list(_ARGS),
        timeout_factor=10,
        # A slow start-up must never turn the Mutant into a timeout: the exit is what these tests pin.
        min_timeout=extra.pop("min_timeout", 30.0),
        warning_threshold=1000,
        cwd=str(root),
        **extra,
    )


@pytest.mark.system
@_EXECUTORS
def test_a_mutant_that_breaks_the_module_at_import_is_killed_and_the_run_goes_on(
    tmp_path, monkeypatch, capsys, forking_requested, executor_line
):
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    src_path, source = write_import_time_lookup_project(str(tmp_path))

    rc = run_mutations(_request(tmp_path, source, forking_requested=forking_requested))

    out = capsys.readouterr().out
    assert rc == 0, out
    # Lines 1 and 2 raise KeyError at import; line 6 is an ordinary Mutant the test kills.
    assert "Killed: 3" in out
    assert "Survived: 0" in out
    assert executor_line in out
    if forking_requested:
        # Three Mutants ran, and the Control run beside them is no Mutant: the counts add up to three.
        counts = re.search(r"fresh import (\d+), swap (\d+), fresh interpreter (\d+)", out)
        assert sum(int(n) for n in counts.groups()) == 3, out
    assert _source_on_disk(src_path) == source


@pytest.mark.system
@_BOTH_EXECUTORS
def test_a_pytest_argv_that_runs_no_test_on_the_original_code_still_aborts_the_run(
    tmp_path, monkeypatch, capsys, forking_requested
):
    """The node id names a test that does not exist: pytest exits 4 on the Mutant and on the Control run."""
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    src_path, source = write_import_time_lookup_project(str(tmp_path))
    measurement = measurement_for(os.path.abspath(src_path), {"tests/test_calc.py::test_gone": [6]}, wall=0.01)

    rc = run_mutations(_request(tmp_path, source, measurement=measurement, forking_requested=forking_requested))

    captured = capsys.readouterr()
    assert rc == 2, captured.out + captured.err
    assert "error: pytest ran no test for a Mutant" in captured.err
    assert f"{src_path}:6" in captured.err
    assert "A Control run of the same pytest args on the original code" in captured.err
    assert "Mutation Report" not in captured.out
    assert _source_on_disk(src_path) == source


@pytest.mark.system
@_BOTH_EXECUTORS
def test_a_node_id_from_a_rootdir_above_the_run_directory_is_rebased_and_the_run_goes_on(
    tmp_path, monkeypatch, capsys, forking_requested
):
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    member = tmp_path / "member"
    member.mkdir()
    src_path, source = write_import_time_lookup_project(str(member))
    record = record_for(rootdir=str(tmp_path), test_files=(str(member / "tests" / "test_calc.py"),))
    measurement = measurement_for(
        os.path.abspath(src_path), {"member/tests/test_calc.py::test_double": [6]}, wall=0.01, record=record
    )

    rc = run_mutations(_request(member, source, measurement=measurement, forking_requested=forking_requested))

    out = capsys.readouterr().out
    assert rc == 0, out
    assert "Killed: 1" in out
    assert "Survived: 0" in out
    assert _source_on_disk(src_path) == source
