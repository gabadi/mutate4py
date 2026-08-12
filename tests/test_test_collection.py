"""Tests for collect_test_node_ids: the node-id collection step that feeds
build_test_context_db (see tests/test_test_context_build.py).
"""

import os

import pytest

from mutate4py._test_collection import (
    TestCollectionError,
    _collect_argv,
    collect_test_node_ids,
    isolated_run_pytest_args,
    rootdir_pytest_args,
)


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


def test_isolated_run_pytest_args_drops_a_relative_existing_path(tmp_path):
    (tmp_path / "test_x.py").write_text("")
    args = ["test_x.py", "-k", "foo"]
    assert isolated_run_pytest_args(args, cwd=str(tmp_path)) == ["-k", "foo"]


def test_isolated_run_pytest_args_keeps_flags_with_no_matching_path(tmp_path):
    args = ["-p", "no:tach", "-x", "-k", "foo"]
    assert isolated_run_pytest_args(args, cwd=str(tmp_path)) == args


def test_isolated_run_pytest_args_keeps_empty_list(tmp_path):
    assert isolated_run_pytest_args([], cwd=str(tmp_path)) == []


@pytest.mark.integration
def test_collect_test_node_ids_finds_every_test_in_the_fixture():
    node_ids = collect_test_node_ids(cwd=FIXTURE_DIR, pytest_args=[])
    assert sorted(n.split("::", 1)[1] for n in node_ids) == ["test_from_a", "test_from_b"]


@pytest.mark.integration
def test_collect_test_node_ids_honours_pytest_args_scoping(tmp_path):
    with pytest.raises(TestCollectionError, match="no tests collected"):
        collect_test_node_ids(cwd=FIXTURE_DIR, pytest_args=["-k", "no_such_test_matches"])


@pytest.mark.integration
def test_collect_test_node_ids_raises_when_nothing_is_collected(tmp_path):
    with pytest.raises(TestCollectionError, match="no tests collected"):
        collect_test_node_ids(cwd=str(tmp_path), pytest_args=[])


@pytest.mark.integration
def test_collect_test_node_ids_raises_on_a_real_collection_error(tmp_path):
    (tmp_path / "test_broken.py").write_text("this is not valid python syntax :::\n")
    with pytest.raises(TestCollectionError, match="pytest collection failed"):
        collect_test_node_ids(cwd=str(tmp_path), pytest_args=[])
