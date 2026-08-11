"""Unit tests for build_test_contexts (_test_context_orchestration.py)."""

import os
import shutil

import pytest

from ._coverage_db_helpers import make_coverage_db, write_text

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_build_test_contexts_success_writes_db_and_returns_0(tmp_path, monkeypatch, capsys):
    import mutate4py._test_context_orchestration as orchestration_mod

    def fake_collect(*, cwd, pytest_args):
        assert cwd == str(tmp_path)
        return ["test_a.py::test_one", "test_b.py::test_two"]

    def fake_build(node_ids, *, cwd, output_db_path, pytest_args=None, isolated_session_runner=None):
        assert node_ids == ["test_a.py::test_one", "test_b.py::test_two"]
        assert cwd == str(tmp_path)
        assert output_db_path == str(tmp_path / "out.db")
        make_coverage_db(output_db_path, [])
        return output_db_path

    monkeypatch.setattr(orchestration_mod, "collect_test_node_ids", fake_collect)
    monkeypatch.setattr(orchestration_mod, "build_test_context_db", fake_build)

    rc = orchestration_mod.build_test_contexts(
        output_db_path=str(tmp_path / "out.db"), cwd=str(tmp_path), pytest_args=[]
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert "out.db" in out
    assert "2" in out


def test_build_test_contexts_collection_failure_returns_1(tmp_path, monkeypatch, capsys):
    import mutate4py._test_context_orchestration as orchestration_mod
    from mutate4py._test_collection import TestCollectionError

    def fake_collect(*, cwd, pytest_args):
        raise TestCollectionError("no tests collected")

    monkeypatch.setattr(orchestration_mod, "collect_test_node_ids", fake_collect)

    rc = orchestration_mod.build_test_contexts(
        output_db_path=str(tmp_path / "out.db"), cwd=str(tmp_path), pytest_args=[]
    )

    assert rc == 1
    assert "no tests collected" in capsys.readouterr().err


def test_build_test_contexts_build_failure_returns_1(tmp_path, monkeypatch, capsys):
    import mutate4py._test_context_orchestration as orchestration_mod
    from mutate4py._test_context_build import TestContextBuildError

    def fake_collect(*, cwd, pytest_args):
        return ["test_a.py::test_one"]

    def fake_build(node_ids, *, cwd, output_db_path, pytest_args=None, isolated_session_runner=None):
        raise TestContextBuildError("combine failed")

    monkeypatch.setattr(orchestration_mod, "collect_test_node_ids", fake_collect)
    monkeypatch.setattr(orchestration_mod, "build_test_context_db", fake_build)

    rc = orchestration_mod.build_test_contexts(
        output_db_path=str(tmp_path / "out.db"), cwd=str(tmp_path), pytest_args=[]
    )

    assert rc == 1
    assert "combine failed" in capsys.readouterr().err


def test_build_test_contexts_strips_a_scoping_path_before_the_isolated_run(tmp_path, monkeypatch):
    """A path passed via pytest_args (the sanctioned way to scope
    --build-test-contexts, since it rejects a positional PATH target) must
    reach collect_test_node_ids, but must NOT reach build_test_context_db's
    per-test invocation, or pytest would run every test under that path
    instead of just the one node ID names (see isolated_run_pytest_args)."""
    import mutate4py._test_context_orchestration as orchestration_mod

    scoped_dir = tmp_path / "sub"
    scoped_dir.mkdir()
    seen_collect_args = {}
    seen_build_args = {}

    def fake_collect(*, cwd, pytest_args):
        seen_collect_args["pytest_args"] = pytest_args
        return ["sub/test_a.py::test_one"]

    def fake_build(node_ids, *, cwd, output_db_path, pytest_args=None, isolated_session_runner=None):
        seen_build_args["pytest_args"] = pytest_args
        make_coverage_db(output_db_path, [])
        return output_db_path

    monkeypatch.setattr(orchestration_mod, "collect_test_node_ids", fake_collect)
    monkeypatch.setattr(orchestration_mod, "build_test_context_db", fake_build)

    rc = orchestration_mod.build_test_contexts(
        output_db_path=str(tmp_path / "out.db"),
        cwd=str(tmp_path),
        pytest_args=[str(scoped_dir), "-p", "no:tach"],
    )

    assert rc == 0
    assert seen_collect_args["pytest_args"] == [str(scoped_dir), "-p", "no:tach"]
    assert seen_build_args["pytest_args"] == ["-p", "no:tach"]


def test_build_test_contexts_skips_rebuild_on_a_fresh_cache(tmp_path, monkeypatch):
    import mutate4py._test_context_orchestration as orchestration_mod

    cwd = str(tmp_path)
    write_text(tmp_path / "test_a.py", "def test_one(): pass\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])

    def fake_collect(*, cwd, pytest_args):
        return ["test_a.py::test_one"]

    def fail_if_called(*args, **kwargs):
        raise AssertionError("build_test_context_db must not run on a cache hit")

    monkeypatch.setattr(orchestration_mod, "collect_test_node_ids", fake_collect)
    monkeypatch.setattr(orchestration_mod, "build_test_context_db", fail_if_called)

    cache = orchestration_mod.build_cache(["test_a.py::test_one"], cwd=cwd, output_db_path=db_path)
    orchestration_mod.write_cache(db_path, cache)

    rc = orchestration_mod.build_test_contexts(output_db_path=db_path, cwd=cwd, pytest_args=[])

    assert rc == 0


def test_build_test_contexts_rebuilds_and_refreshes_the_cache_when_stale(tmp_path, monkeypatch):
    import mutate4py._test_context_orchestration as orchestration_mod

    cwd = str(tmp_path)
    test_file = tmp_path / "test_a.py"
    write_text(test_file, "def test_one(): pass\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])

    def fake_collect(*, cwd, pytest_args):
        return ["test_a.py::test_one"]

    calls = []

    def fake_build(node_ids, *, cwd, output_db_path, pytest_args=None, isolated_session_runner=None):
        calls.append(node_ids)
        os.remove(output_db_path)
        make_coverage_db(output_db_path, [])
        return output_db_path

    monkeypatch.setattr(orchestration_mod, "collect_test_node_ids", fake_collect)
    monkeypatch.setattr(orchestration_mod, "build_test_context_db", fake_build)

    stale_cache = {"version": 2, "node_ids": ["test_a.py::test_two"], "py_files": {}, "source_files": {}}
    orchestration_mod.write_cache(db_path, stale_cache)

    rc = orchestration_mod.build_test_contexts(output_db_path=db_path, cwd=cwd, pytest_args=[])

    assert rc == 0
    assert calls == [["test_a.py::test_one"]]
    from mutate4py._test_context_cache import read_cache

    refreshed, ok = read_cache(db_path)
    assert ok is True
    assert refreshed["node_ids"] == ["test_a.py::test_one"]


def test_build_test_contexts_discards_the_cache_when_the_rebuild_fails(tmp_path, monkeypatch, capsys):
    """A build that dies partway may have already overwritten the db, so the
    old cache must not survive to vouch for it."""
    import mutate4py._test_context_orchestration as orchestration_mod
    from mutate4py._test_context_build import TestContextBuildError
    from mutate4py._test_context_cache import cache_path

    cwd = str(tmp_path)
    write_text(tmp_path / "test_a.py", "def test_one(): pass\n")
    db_path = str(tmp_path / "out.db")
    make_coverage_db(db_path, [])

    def fake_collect(*, cwd, pytest_args):
        return ["test_a.py::test_one"]

    def fake_build(*args, **kwargs):
        raise TestContextBuildError("boom")

    monkeypatch.setattr(orchestration_mod, "collect_test_node_ids", fake_collect)
    monkeypatch.setattr(orchestration_mod, "build_test_context_db", fake_build)
    orchestration_mod.write_cache(db_path, {"version": 2, "node_ids": [], "py_files": {}, "source_files": {}})

    rc = orchestration_mod.build_test_contexts(output_db_path=db_path, cwd=cwd, pytest_args=[])

    assert rc == 1
    assert os.path.isfile(cache_path(db_path)) is False


@pytest.mark.integration
def test_build_test_contexts_second_run_skips_rebuild_then_invalidates_on_change(tmp_path):
    from mutate4py._test_context_orchestration import build_test_contexts

    fixture_src = os.path.join(REPO_ROOT, "tests", "fixtures", "overlapping_coverage")
    work_dir = tmp_path / "work"
    shutil.copytree(fixture_src, work_dir)
    db_path = str(tmp_path / "combined.coverage")

    rc = build_test_contexts(output_db_path=db_path, cwd=str(work_dir), pytest_args=[])
    assert rc == 0
    first_mtime = os.path.getmtime(db_path)

    rc = build_test_contexts(output_db_path=db_path, cwd=str(work_dir), pytest_args=[])
    assert rc == 0
    assert os.path.getmtime(db_path) == first_mtime, "unchanged inputs must skip the rebuild"

    test_a = work_dir / "test_a.py"
    write_text(test_a, test_a.read_text() + "\n\ndef test_extra():\n    assert True\n")
    rc = build_test_contexts(output_db_path=db_path, cwd=str(work_dir), pytest_args=[])
    assert rc == 0
    assert os.path.getmtime(db_path) != first_mtime, "a changed test file must trigger a rebuild"
    second_mtime = os.path.getmtime(db_path)

    shared_py = work_dir / "shared.py"
    write_text(shared_py, shared_py.read_text().replace("return 1", "return 1  # changed"))
    rc = build_test_contexts(output_db_path=db_path, cwd=str(work_dir), pytest_args=[])
    assert rc == 0
    assert os.path.getmtime(db_path) != second_mtime, "a changed source file must trigger a rebuild"


@pytest.mark.integration
def test_build_test_contexts_end_to_end_narrows_to_every_covering_test(tmp_path):
    from mutate4py._test_context_orchestration import build_test_contexts
    from mutate4py._test_selection import TestContextDB

    fixture_dir = os.path.join(REPO_ROOT, "tests", "fixtures", "overlapping_coverage")
    db_path = str(tmp_path / "combined.coverage")

    rc = build_test_contexts(output_db_path=db_path, cwd=fixture_dir, pytest_args=[])

    assert rc == 0
    db = TestContextDB(db_path)
    try:
        shared_py = os.path.join(fixture_dir, "shared.py")
        outcome, node_ids = db.tests_for_line(shared_py, 2)
        assert outcome == "narrowed"
        assert sorted(n.split("::", 1)[1] for n in node_ids) == ["test_from_a", "test_from_b"]
    finally:
        db.close()
