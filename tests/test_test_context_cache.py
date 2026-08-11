"""Unit tests for _test_context_cache.py (--build-test-contexts staleness cache)."""

import json
import os

import mutate4py._test_context_cache as cache_mod
from mutate4py._test_context_cache import (
    build_cache,
    cache_path,
    discard_cache,
    is_cache_fresh,
    read_cache,
    should_skip_rebuild,
    write_cache,
)

from ._coverage_db_helpers import make_coverage_db, write_text


def _unreadable_py(path):
    """A .py file that os.walk lists but open() refuses, without relying on
    chmod (which a root-run test suite would ignore): a dangling symlink."""
    os.symlink(str(path) + ".nonexistent-target", path)


def test_cache_path_appends_suffix():
    assert cache_path("/tmp/out.db") == "/tmp/out.db.test-context-cache.json"


def test_build_cache_hashes_test_and_source_files(tmp_path):
    cwd = str(tmp_path)
    write_text(tmp_path / "test_a.py", "def test_one(): pass\n")
    write_text(tmp_path / "shared.py", "def shared(): return 1\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [str(tmp_path / "shared.py")])

    cache = build_cache(["test_a.py::test_one"], cwd=cwd, output_db_path=db_path)

    assert cache["version"] == 2
    assert cache["node_ids"] == ["test_a.py::test_one"]
    assert str(tmp_path / "test_a.py") in cache["py_files"]
    assert set(cache["source_files"]) == {str(tmp_path / "shared.py")}


def test_build_cache_includes_conftest_in_an_ancestor_directory(tmp_path):
    cwd = str(tmp_path)
    sub = tmp_path / "sub"
    sub.mkdir()
    write_text(tmp_path / "conftest.py", "import pytest\n")
    write_text(sub / "test_a.py", "def test_one(): pass\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])

    cache = build_cache(["sub/test_a.py::test_one"], cwd=cwd, output_db_path=db_path)

    assert str(tmp_path / "conftest.py") in cache["py_files"]


def test_build_cache_includes_test_support_files_beside_the_test(tmp_path):
    cwd = str(tmp_path)
    sub = tmp_path / "sub"
    sub.mkdir()
    write_text(sub / "helpers.py", "def make(): return object()\n")
    write_text(sub / "test_a.py", "from sub.helpers import make\ndef test_one(): make()\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])

    cache = build_cache(["sub/test_a.py::test_one"], cwd=cwd, output_db_path=db_path)

    assert str(sub / "helpers.py") in cache["py_files"]


def test_build_cache_includes_test_support_files_in_a_subdirectory(tmp_path):
    """tests/helpers/factories.py imported by tests/test_a.py — a child of the
    test's own directory, not an ancestor of it."""
    cwd = str(tmp_path)
    tests_dir = tmp_path / "tests"
    helpers_dir = tests_dir / "helpers"
    helpers_dir.mkdir(parents=True)
    write_text(helpers_dir / "factories.py", "def make(): return object()\n")
    write_text(tests_dir / "test_a.py", "from tests.helpers.factories import make\ndef test_one(): make()\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])

    cache = build_cache(["tests/test_a.py::test_one"], cwd=cwd, output_db_path=db_path)

    assert str(helpers_dir / "factories.py") in cache["py_files"]


def test_build_cache_includes_test_support_files_in_a_sibling_subdirectory(tmp_path):
    """tests/helpers/factories.py imported by tests/unit/test_a.py — neither an
    ancestor of the test's directory nor a child of it."""
    cwd = str(tmp_path)
    unit_dir = tmp_path / "tests" / "unit"
    helpers_dir = tmp_path / "tests" / "helpers"
    unit_dir.mkdir(parents=True)
    helpers_dir.mkdir(parents=True)
    write_text(helpers_dir / "factories.py", "def make(): return object()\n")
    write_text(unit_dir / "test_a.py", "from tests.helpers.factories import make\ndef test_one(): make()\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])

    cache = build_cache(["tests/unit/test_a.py::test_one"], cwd=cwd, output_db_path=db_path)

    assert str(helpers_dir / "factories.py") in cache["py_files"]


def test_build_cache_prunes_dot_directories_and_bytecode_caches(tmp_path):
    cwd = str(tmp_path)
    write_text(tmp_path / "test_a.py", "def test_one(): pass\n")
    for pruned in (".venv", "__pycache__", "node_modules", "venv"):
        (tmp_path / pruned).mkdir()
        write_text(tmp_path / pruned / "vendored.py", "x = 1\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])

    cache = build_cache(["test_a.py::test_one"], cwd=cwd, output_db_path=db_path)

    assert [p for p in cache["py_files"] if "vendored.py" in p] == []


def test_build_cache_hashes_non_utf8_test_file_without_crashing(tmp_path):
    cwd = str(tmp_path)
    with open(tmp_path / "test_a.py", "wb") as f:
        f.write(b"# -*- coding: latin-1 -*-\nx = '\xe9'\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])

    cache = build_cache(["test_a.py::test_one"], cwd=cwd, output_db_path=db_path)

    assert cache["py_files"][str(tmp_path / "test_a.py")] is not None


def test_build_cache_records_a_missing_test_file_as_unhashable(tmp_path):
    cwd = str(tmp_path)
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])

    cache = build_cache(["missing.py::test_one"], cwd=cwd, output_db_path=db_path)

    assert cache["py_files"][str(tmp_path / "missing.py")] is None


def test_build_cache_records_an_unhashable_config_file_without_dropping_the_rest(tmp_path, monkeypatch):
    cwd = str(tmp_path)
    write_text(tmp_path / "test_a.py", "def test_one(): pass\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])
    monkeypatch.setattr(cache_mod, "_coverage_config_paths", lambda *, cwd: {"missing_config.toml"})

    cache = build_cache(["test_a.py::test_one"], cwd=cwd, output_db_path=db_path)

    assert cache["config_files"] == {"missing_config.toml": None}
    assert cache["py_files"][str(tmp_path / "test_a.py")] is not None


def test_build_cache_records_an_unhashable_covered_source_file_as_none(tmp_path, monkeypatch):
    cwd = str(tmp_path)
    write_text(tmp_path / "test_a.py", "def test_one(): pass\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])
    missing_source = str(tmp_path / "missing_source.py")
    monkeypatch.setattr(cache_mod, "_covered_source_paths", lambda db_path: [missing_source])

    cache = build_cache(["test_a.py::test_one"], cwd=cwd, output_db_path=db_path)

    assert cache["source_files"] == {missing_source: None}


def test_an_unreadable_project_file_does_not_disable_caching(tmp_path):
    """One permission-denied .py file must cost a single unhashable entry, not
    the whole fingerprint — otherwise caching is off for good."""
    cwd = str(tmp_path)
    write_text(tmp_path / "test_a.py", "def test_one(): pass\n")
    _unreadable_py(tmp_path / "locked.py")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])

    write_cache(db_path, build_cache(["test_a.py::test_one"], cwd=cwd, output_db_path=db_path))

    assert should_skip_rebuild(output_db_path=db_path, node_ids=["test_a.py::test_one"], cwd=cwd) is True


def test_build_cache_tracks_a_test_file_outside_the_cwd_tree(tmp_path):
    cwd = str(tmp_path / "project")
    os.makedirs(cwd)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    test_file = outside_dir / "test_a.py"
    write_text(test_file, "def test_one(): pass\n")
    db_path = str(tmp_path / "project" / "out.db")
    make_coverage_db(db_path, [])

    cache = build_cache([f"{test_file}::test_one"], cwd=cwd, output_db_path=db_path)

    assert cache["py_files"][str(test_file)] is not None


def test_write_and_read_cache_round_trip(tmp_path):
    db_path = str(tmp_path / "out.db")
    cache = {"version": 2, "node_ids": ["a.py::t"], "py_files": {"a.py": "h1"}, "source_files": {"b.py": "h2"}}

    write_cache(db_path, cache)
    parsed, ok = read_cache(db_path)

    assert ok is True
    assert parsed == cache
    assert os.path.isfile(cache_path(db_path))


def test_write_and_read_cache_round_trips_unhashable_entries(tmp_path):
    """An unhashable entry must survive JSON as None, or every run after one
    would see a spurious difference and rebuild forever."""
    db_path = str(tmp_path / "out.db")

    write_cache(db_path, {"version": 2, "node_ids": [], "py_files": {"a.py": None}, "source_files": {}})
    parsed, _ = read_cache(db_path)

    assert parsed["py_files"] == {"a.py": None}


def test_read_cache_missing_file_returns_not_ok(tmp_path):
    parsed, ok = read_cache(str(tmp_path / "out.db"))
    assert (parsed, ok) == (None, False)


def test_read_cache_corrupt_json_returns_not_ok(tmp_path):
    db_path = str(tmp_path / "out.db")
    write_text(cache_path(db_path), "{not valid json")

    parsed, ok = read_cache(db_path)

    assert (parsed, ok) == (None, False)


def test_read_cache_non_dict_json_returns_not_ok(tmp_path):
    db_path = str(tmp_path / "out.db")
    write_text(cache_path(db_path), json.dumps([1, 2, 3]))

    parsed, ok = read_cache(db_path)

    assert (parsed, ok) == (None, False)


def test_is_cache_fresh_true_when_nothing_changed(tmp_path):
    cwd = str(tmp_path)
    write_text(tmp_path / "test_a.py", "def test_one(): pass\n")
    write_text(tmp_path / "shared.py", "def shared(): return 1\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [str(tmp_path / "shared.py")])
    cache = build_cache(["test_a.py::test_one"], cwd=cwd, output_db_path=db_path)

    assert is_cache_fresh(cache, node_ids=["test_a.py::test_one"], cwd=cwd) is True


def test_is_cache_fresh_false_for_a_cache_written_by_an_older_version(tmp_path):
    cwd = str(tmp_path)
    write_text(tmp_path / "test_a.py", "def test_one(): pass\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])
    v1_cache = {"version": 1, "node_ids": ["test_a.py::test_one"], "test_files": {}, "source_files": {}}

    assert is_cache_fresh(v1_cache, node_ids=["test_a.py::test_one"], cwd=cwd) is False


def test_is_cache_fresh_false_for_a_newer_version_reusing_todays_key_names(tmp_path):
    """A future format that keeps the same keys must still be rejected — what
    the fields mean is version-specific."""
    cwd = str(tmp_path)
    write_text(tmp_path / "test_a.py", "def test_one(): pass\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])
    cache = build_cache(["test_a.py::test_one"], cwd=cwd, output_db_path=db_path)
    assert is_cache_fresh(cache, node_ids=["test_a.py::test_one"], cwd=cwd) is True

    cache["version"] = 3

    assert is_cache_fresh(cache, node_ids=["test_a.py::test_one"], cwd=cwd) is False


def test_is_cache_fresh_false_when_node_ids_changed(tmp_path):
    cwd = str(tmp_path)
    write_text(tmp_path / "test_a.py", "def test_one(): pass\ndef test_two(): pass\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])
    cache = build_cache(["test_a.py::test_one"], cwd=cwd, output_db_path=db_path)

    fresh = is_cache_fresh(cache, node_ids=["test_a.py::test_one", "test_a.py::test_two"], cwd=cwd)

    assert fresh is False


def test_is_cache_fresh_false_when_test_file_content_changed(tmp_path):
    cwd = str(tmp_path)
    test_file = tmp_path / "test_a.py"
    write_text(test_file, "def test_one(): pass\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])
    cache = build_cache(["test_a.py::test_one"], cwd=cwd, output_db_path=db_path)

    write_text(test_file, "def test_one(): assert 1 == 1\n")

    assert is_cache_fresh(cache, node_ids=["test_a.py::test_one"], cwd=cwd) is False


def test_is_cache_fresh_false_when_source_file_content_changed(tmp_path):
    cwd = str(tmp_path)
    write_text(tmp_path / "test_a.py", "def test_one(): pass\n")
    source_file = tmp_path / "shared.py"
    write_text(source_file, "def shared(): return 1\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [str(source_file)])
    cache = build_cache(["test_a.py::test_one"], cwd=cwd, output_db_path=db_path)

    write_text(source_file, "def shared(): return 2\n")

    assert is_cache_fresh(cache, node_ids=["test_a.py::test_one"], cwd=cwd) is False


def test_is_cache_fresh_false_when_conftest_content_changed(tmp_path):
    cwd = str(tmp_path)
    sub = tmp_path / "sub"
    sub.mkdir()
    conftest = tmp_path / "conftest.py"
    write_text(conftest, "import pytest\n")
    write_text(sub / "test_a.py", "def test_one(): pass\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])
    cache = build_cache(["sub/test_a.py::test_one"], cwd=cwd, output_db_path=db_path)

    write_text(conftest, "import pytest\n# changed\n")

    assert is_cache_fresh(cache, node_ids=["sub/test_a.py::test_one"], cwd=cwd) is False


def test_is_cache_fresh_false_when_a_subdirectory_support_file_changed(tmp_path):
    cwd = str(tmp_path)
    helpers_dir = tmp_path / "tests" / "helpers"
    helpers_dir.mkdir(parents=True)
    factories = helpers_dir / "factories.py"
    write_text(factories, "def make(): return object()\n")
    write_text(tmp_path / "tests" / "test_a.py", "from tests.helpers.factories import make\ndef test_one(): make()\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])
    cache = build_cache(["tests/test_a.py::test_one"], cwd=cwd, output_db_path=db_path)

    write_text(factories, "def make(): return object()  # changed\n")

    assert is_cache_fresh(cache, node_ids=["tests/test_a.py::test_one"], cwd=cwd) is False


def test_is_cache_fresh_false_when_a_project_file_is_added(tmp_path):
    cwd = str(tmp_path)
    write_text(tmp_path / "test_a.py", "def test_one(): pass\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])
    cache = build_cache(["test_a.py::test_one"], cwd=cwd, output_db_path=db_path)

    write_text(tmp_path / "newly_added.py", "x = 1\n")

    assert is_cache_fresh(cache, node_ids=["test_a.py::test_one"], cwd=cwd) is False


def test_is_cache_fresh_false_when_an_unreadable_file_becomes_readable(tmp_path):
    cwd = str(tmp_path)
    write_text(tmp_path / "test_a.py", "def test_one(): pass\n")
    _unreadable_py(tmp_path / "locked.py")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])
    cache = build_cache(["test_a.py::test_one"], cwd=cwd, output_db_path=db_path)

    write_text(tmp_path / "locked.py.nonexistent-target", "x = 1\n")

    assert is_cache_fresh(cache, node_ids=["test_a.py::test_one"], cwd=cwd) is False


def test_is_cache_fresh_false_when_coverage_config_added(tmp_path):
    cwd = str(tmp_path)
    write_text(tmp_path / "test_a.py", "def test_one(): pass\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])
    cache = build_cache(["test_a.py::test_one"], cwd=cwd, output_db_path=db_path)

    write_text(tmp_path / "pyproject.toml", "[tool.coverage.run]\nbranch = true\n")

    assert is_cache_fresh(cache, node_ids=["test_a.py::test_one"], cwd=cwd) is False


def test_is_cache_fresh_false_when_a_covered_source_file_outside_cwd_changed(tmp_path):
    cwd = str(tmp_path / "project")
    os.makedirs(cwd)
    write_text(tmp_path / "project" / "test_a.py", "def test_one(): pass\n")
    outside = tmp_path / "installed"
    outside.mkdir()
    source_file = outside / "shared.py"
    write_text(source_file, "def shared(): return 1\n")
    db_path = str(tmp_path / "project" / "out.db")
    make_coverage_db(db_path, [str(source_file)])
    cache = build_cache(["test_a.py::test_one"], cwd=cwd, output_db_path=db_path)
    # Outside cwd the project sweep never reaches it — only the source_files
    # loop (is_cache_fresh's last check) can catch this edit.
    assert str(source_file) not in cache["py_files"]

    write_text(source_file, "def shared(): return 2\n")

    assert is_cache_fresh(cache, node_ids=["test_a.py::test_one"], cwd=cwd) is False


def test_is_cache_fresh_false_when_source_file_removed(tmp_path):
    cwd = str(tmp_path)
    write_text(tmp_path / "test_a.py", "def test_one(): pass\n")
    source_file = tmp_path / "shared.py"
    write_text(source_file, "def shared(): return 1\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [str(source_file)])
    cache = build_cache(["test_a.py::test_one"], cwd=cwd, output_db_path=db_path)

    os.remove(source_file)

    assert is_cache_fresh(cache, node_ids=["test_a.py::test_one"], cwd=cwd) is False


def test_should_skip_rebuild_false_when_db_does_not_exist(tmp_path):
    result = should_skip_rebuild(output_db_path=str(tmp_path / "out.db"), node_ids=["a.py::t"], cwd=str(tmp_path))
    assert result is False


def test_should_skip_rebuild_false_when_cache_is_stale(tmp_path):
    cwd = str(tmp_path)
    write_text(tmp_path / "test_a.py", "def test_one(): pass\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])
    write_cache(db_path, {"version": 2, "node_ids": ["different"], "py_files": {}, "source_files": {}})

    assert should_skip_rebuild(output_db_path=db_path, node_ids=["test_a.py::test_one"], cwd=cwd) is False


def test_should_skip_rebuild_true_when_cache_is_fresh(tmp_path):
    cwd = str(tmp_path)
    write_text(tmp_path / "test_a.py", "def test_one(): pass\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])
    write_cache(db_path, build_cache(["test_a.py::test_one"], cwd=cwd, output_db_path=db_path))

    assert should_skip_rebuild(output_db_path=db_path, node_ids=["test_a.py::test_one"], cwd=cwd) is True


def test_should_skip_rebuild_false_when_db_exists_but_cache_is_absent(tmp_path):
    cwd = str(tmp_path)
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])

    result = should_skip_rebuild(output_db_path=db_path, node_ids=["a.py::t"], cwd=cwd)

    assert result is False


def test_discard_cache_removes_existing_cache_file(tmp_path):
    db_path = str(tmp_path / "out.db")
    write_cache(db_path, {"version": 2, "node_ids": [], "py_files": {}, "source_files": {}})

    discard_cache(db_path)

    assert os.path.isfile(cache_path(db_path)) is False


def test_discard_cache_is_a_noop_when_cache_is_absent(tmp_path):
    db_path = str(tmp_path / "out.db")

    discard_cache(db_path)

    assert os.path.isfile(cache_path(db_path)) is False
