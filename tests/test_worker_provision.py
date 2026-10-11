"""Unit tests for Worker venv distribution parity and uv pinning (ADR 0015)."""

import json
import os
import subprocess
import sys

import pytest

import mutate4py._worker_provision as provision_mod
from mutate4py._worker_protocol import WorkerProcessError
from mutate4py._worker_provision import _copy_tree, _provision_venv, check_worker_distributions
from mutate4py._workers import _required_worker_distributions


def _fake_worker_python(worker_root, distributions):
    """A stand-in .venv/bin/python that answers the distribution probe with `distributions`."""
    bin_dir = os.path.join(str(worker_root), ".venv", "bin")
    os.makedirs(bin_dir)
    script = os.path.join(bin_dir, "python")
    with open(script, "w") as f:
        f.write(f"#!/bin/sh\necho '{json.dumps(distributions)}'\n")
    os.chmod(script, 0o755)


@pytest.mark.component
def test_worker_distributions_missing_a_required_one_raises_naming_it(tmp_path):
    _fake_worker_python(tmp_path, ["pytest"])
    with pytest.raises(WorkerProcessError, match="lacks pytest-cov") as exc:
        check_worker_distributions(str(tmp_path), frozenset({"pytest", "pytest-cov"}))
    assert "dev dependency group" in str(exc.value)


@pytest.mark.component
def test_worker_distributions_with_every_required_one_present_passes(tmp_path):
    _fake_worker_python(tmp_path, ["pytest", "pytest-cov", "coverage"])
    check_worker_distributions(str(tmp_path), frozenset({"pytest", "pytest-cov"}))


@pytest.mark.unit
def test_worker_distributions_with_nothing_required_runs_no_probe(tmp_path, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("no distribution probe when nothing is required")

    monkeypatch.setattr(subprocess, "run", refuse)
    check_worker_distributions(str(tmp_path), frozenset())


@pytest.mark.component
def test_worker_distributions_probe_that_cannot_run_raises_a_worker_process_error(tmp_path):
    with pytest.raises(WorkerProcessError, match="could not list its distributions"):
        check_worker_distributions(str(tmp_path), frozenset({"pytest"}))


@pytest.mark.unit
def test_provision_venv_pins_uv_to_the_orchestrator_interpreter(tmp_path, monkeypatch):
    calls = []

    def record(cmd, **kwargs):
        calls.append((cmd, kwargs.get("cwd")))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", record)
    monkeypatch.setattr(provision_mod, "check_worker_python", lambda root: None)
    monkeypatch.setattr(provision_mod, "check_worker_distributions", lambda root, required: None)

    _provision_venv(str(tmp_path), frozenset())

    assert [cmd for cmd, _ in calls] == [
        ["uv", "venv", "--python", sys.executable],
        ["uv", "sync", "--python", sys.executable],
    ]
    assert all(cwd == str(tmp_path) for _, cwd in calls)


@pytest.mark.unit
def test_provision_venv_checks_the_distributions_it_is_given(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    )
    monkeypatch.setattr(provision_mod, "check_worker_python", lambda root: None)
    monkeypatch.setattr(
        provision_mod, "check_worker_distributions", lambda root, required: seen.append((root, required))
    )

    _provision_venv(str(tmp_path), frozenset({"pytest"}))

    assert seen == [(str(tmp_path), frozenset({"pytest"}))]


@pytest.mark.unit
def test_required_distributions_are_empty_when_the_orchestrator_runs_outside_the_project_venv(tmp_path):
    assert _required_worker_distributions(str(tmp_path)) == frozenset()


@pytest.mark.unit
def test_required_distributions_are_the_project_environment_without_mutate4py(tmp_path):
    os.symlink(sys.prefix, os.path.join(tmp_path, ".venv"))
    required = _required_worker_distributions(str(tmp_path))
    assert "pytest" in required
    assert "mutate4py" not in required


@pytest.mark.unit
def test_check_worker_distributions_branches_without_a_process(monkeypatch):
    """Unit-tier twin of the component tests: the probe is stubbed, so lcov (test-unit only,
    read by `crap`) covers every branch of check_worker_distributions."""
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout='["pytest", "pytest-cov"]', stderr="")

    monkeypatch.setattr(provision_mod.subprocess, "run", fake_run)
    check_worker_distributions("/w", frozenset())
    assert calls == []
    check_worker_distributions("/w", frozenset({"pytest"}))
    assert len(calls) == 1
    with pytest.raises(WorkerProcessError, match="lacks pytest-mock"):
        check_worker_distributions("/w", frozenset({"pytest", "pytest-mock"}))


@pytest.mark.unit
def test_check_worker_distributions_maps_probe_failure_without_a_process(monkeypatch):
    def failing_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(provision_mod.subprocess, "run", failing_run)
    with pytest.raises(WorkerProcessError, match="could not list its distributions"):
        check_worker_distributions("/w", frozenset({"pytest"}))


@pytest.mark.unit
def test_copy_tree_recreates_dir_symlink_outside_tree(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "x.py").write_text("v")
    src = tmp_path / "src"
    src.mkdir()
    (src / "vendored").symlink_to("../shared")
    dst = tmp_path / "deep" / "a" / "b" / "dst"
    _copy_tree(str(src), str(dst))
    assert (dst / "vendored").is_symlink()
    assert (dst / "vendored" / "x.py").read_text() == "v"


@pytest.mark.unit
def test_copy_tree_in_tree_dir_symlink_points_into_the_copy(tmp_path):
    src = tmp_path / "src"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "m.py").write_text("x = 1")
    (src / "alias").symlink_to("pkg")
    dst = tmp_path / "dst"
    _copy_tree(str(src), str(dst))
    assert (dst / "alias").is_symlink()
    assert os.path.realpath(dst / "alias") == os.path.realpath(dst / "pkg")


@pytest.mark.unit
def test_copy_tree_recreates_dangling_symlink(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "broken").symlink_to("missing")
    dst = tmp_path / "dst"
    _copy_tree(str(src), str(dst))
    assert (dst / "broken").is_symlink()
