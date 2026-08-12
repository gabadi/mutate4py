"""Tests for collect_test_node_ids: the node-id collection step that feeds
build_test_context_db (see tests/test_test_context_build.py).
"""

import os
import subprocess

import pytest

from mutate4py._test_collection import (
    TestCollectionError,
    _collect_argv,
    collect_pytest_args,
    collect_test_node_ids,
    isolated_run_pytest_args,
    node_ids_from_collect_result,
    rootdir_pytest_args,
)


def _collect_result(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "overlapping_coverage")


@pytest.mark.unit
def test_collect_argv_names_the_collect_only_quiet_pass():
    argv = _collect_argv(["-k", "foo"], python_executable="python")
    assert argv == ["python", "-m", "pytest", "--collect-only", "-q", "-k", "foo"]


@pytest.mark.unit
def test_rootdir_pytest_args_pins_rootdir_to_cwd():
    assert rootdir_pytest_args("/some/dir") == ["--rootdir=/some/dir"]


@pytest.mark.unit
def test_isolated_run_pytest_args_drops_an_existing_path(tmp_path):
    scoped_dir = tmp_path / "sub"
    scoped_dir.mkdir()
    args = [str(scoped_dir), "-p", "no:tach"]
    assert isolated_run_pytest_args(args, cwd=str(tmp_path)) == ["-p", "no:tach"]


@pytest.mark.unit
def test_isolated_run_pytest_args_drops_a_relative_existing_path(tmp_path):
    (tmp_path / "test_x.py").write_text("")
    args = ["test_x.py", "-k", "foo"]
    assert isolated_run_pytest_args(args, cwd=str(tmp_path)) == ["-k", "foo"]


@pytest.mark.unit
def test_isolated_run_pytest_args_keeps_flags_with_no_matching_path(tmp_path):
    args = ["-p", "no:tach", "-x", "-k", "foo"]
    assert isolated_run_pytest_args(args, cwd=str(tmp_path)) == args


@pytest.mark.unit
def test_isolated_run_pytest_args_keeps_empty_list(tmp_path):
    assert isolated_run_pytest_args([], cwd=str(tmp_path)) == []


@pytest.mark.unit
def test_collect_pytest_args_appends_the_pinned_rootdir():
    assert collect_pytest_args(["-k", "foo"], cwd="/some/dir") == ["-k", "foo", "--rootdir=/some/dir"]


@pytest.mark.unit
def test_collect_pytest_args_treats_none_as_no_args():
    assert collect_pytest_args(None, cwd="/some/dir") == ["--rootdir=/some/dir"]


# ── node_ids_from_collect_result ──────────────────────────────────────────


@pytest.mark.unit
def test_node_ids_from_collect_result_keeps_only_node_id_lines():
    stdout = "tests/test_a.py::test_one\ntests/test_a.py::test_two\n\n2 tests collected in 0.01s\n"
    node_ids = node_ids_from_collect_result(_collect_result(0, stdout), cwd="/w", pytest_args=[])
    assert node_ids == ["tests/test_a.py::test_one", "tests/test_a.py::test_two"]


@pytest.mark.unit
def test_node_ids_from_collect_result_strips_surrounding_whitespace():
    node_ids = node_ids_from_collect_result(
        _collect_result(0, "  tests/test_a.py::test_one  \n"), cwd="/w", pytest_args=[]
    )
    assert node_ids == ["tests/test_a.py::test_one"]


@pytest.mark.unit
def test_node_ids_from_collect_result_accepts_the_no_tests_collected_exit_code():
    """Exit 5 with node IDs on stdout is a scoping artefact, not a failure."""
    result = _collect_result(5, "tests/test_a.py::test_one\n")
    assert node_ids_from_collect_result(result, cwd="/w", pytest_args=[]) == ["tests/test_a.py::test_one"]


@pytest.mark.unit
def test_node_ids_from_collect_result_raises_on_a_failing_collection_pass():
    result = _collect_result(2, "some stdout", "some stderr")
    with pytest.raises(TestCollectionError, match="pytest collection failed \\(exit 2\\)") as exc:
        node_ids_from_collect_result(result, cwd="/w", pytest_args=[])
    assert "some stdout" in str(exc.value)
    assert "some stderr" in str(exc.value)


@pytest.mark.unit
def test_node_ids_from_collect_result_raises_when_no_node_id_line_is_found():
    result = _collect_result(5, "no tests ran in 0.01s\n")
    with pytest.raises(TestCollectionError, match="no tests collected in '/w'") as exc:
        node_ids_from_collect_result(result, cwd="/w", pytest_args=["-k", "nope"])
    assert "-k" in str(exc.value)


@pytest.mark.component
def test_collect_test_node_ids_finds_every_test_in_the_fixture():
    node_ids = collect_test_node_ids(cwd=FIXTURE_DIR, pytest_args=[])
    assert sorted(n.split("::", 1)[1] for n in node_ids) == ["test_from_a", "test_from_b"]


@pytest.mark.component
def test_collect_test_node_ids_honours_pytest_args_scoping(tmp_path):
    with pytest.raises(TestCollectionError, match="no tests collected"):
        collect_test_node_ids(cwd=FIXTURE_DIR, pytest_args=["-k", "no_such_test_matches"])


@pytest.mark.component
def test_collect_test_node_ids_raises_when_nothing_is_collected(tmp_path):
    with pytest.raises(TestCollectionError, match="no tests collected"):
        collect_test_node_ids(cwd=str(tmp_path), pytest_args=[])


@pytest.mark.component
def test_collect_test_node_ids_raises_on_a_real_collection_error(tmp_path):
    (tmp_path / "test_broken.py").write_text("this is not valid python syntax :::\n")
    with pytest.raises(TestCollectionError, match="pytest collection failed"):
        collect_test_node_ids(cwd=str(tmp_path), pytest_args=[])
