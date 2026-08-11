"""Unit tests for build_test_contexts (_test_context_orchestration.py)."""

import os

import pytest

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
