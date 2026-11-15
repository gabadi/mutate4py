"""Unit tests for _pytest_session.py: the conftests a run may load."""

import os

import pytest

from mutate4py._pytest_session import run_conftests


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    return str(path)


@pytest.mark.unit
def test_run_conftests_lists_those_above_and_beneath_each_collection_root(tmp_path):
    above = _touch(tmp_path / "conftest.py")
    beneath = _touch(tmp_path / "tests" / "sub" / "conftest.py")
    nearest = _touch(tmp_path / "tests" / "conftest.py")
    _touch(tmp_path / "elsewhere" / "conftest.py")

    found = run_conftests(str(tmp_path), ["tests"], [str(tmp_path)])

    assert sorted(found) == sorted([above, nearest, beneath])


@pytest.mark.unit
def test_run_conftests_stops_above_at_the_bound(tmp_path):
    inside = _touch(tmp_path / "proj" / "conftest.py")
    _touch(tmp_path / "conftest.py")

    found = run_conftests(str(tmp_path / "proj"), [], [str(tmp_path / "proj")])

    assert found == [inside]


@pytest.mark.unit
def test_run_conftests_reaches_the_filesystem_root_without_a_bound(tmp_path):
    outer = _touch(tmp_path / "conftest.py")
    inner = _touch(tmp_path / "proj" / "tests" / "conftest.py")

    found = run_conftests(str(tmp_path / "proj"), ["tests"], None)

    assert outer in found
    assert inner in found


@pytest.mark.unit
def test_run_conftests_skips_pruned_directories_and_lists_each_file_once(tmp_path):
    _touch(tmp_path / ".venv" / "conftest.py")
    _touch(tmp_path / "node_modules" / "conftest.py")
    top = _touch(tmp_path / "conftest.py")

    found = run_conftests(str(tmp_path), [], [str(tmp_path)])

    assert found == [top]
    assert len(found) == len(set(found))


@pytest.mark.unit
def test_run_conftests_for_a_root_that_is_a_file_lists_the_chain_above_it(tmp_path):
    chain = _touch(tmp_path / "tests" / "conftest.py")
    _touch(tmp_path / "tests" / "test_a.py")

    found = run_conftests(str(tmp_path), [os.path.join("tests", "test_a.py")], [str(tmp_path)])

    assert found == [chain]
