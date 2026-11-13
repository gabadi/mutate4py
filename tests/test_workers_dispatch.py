"""Unit tests for run_parallel's dispatch: the plan's selection tally reaches each
Worker, a test-context db disagreement aborts before any Worker is provisioned,
executors are primed per Worker, and the dogfood run scores the same under
workers as serially. Internals are covered in test_workers.py."""

import os
import shutil
import subprocess

import pytest

from mutate4py._discovery import discover_sites
from mutate4py._test_dispatch import TestSelectionError as SelectionError
from mutate4py._test_dispatch import TimeoutPolicy
from mutate4py._worker_provision import _SKIP_ENTRIES
from mutate4py._workers import ParallelRunError, ParallelRunRequest, run_parallel

from ._worker_fakes_helpers import FakeExecutor, noop_on_result

_FIVE_SECOND_POLICY = TimeoutPolicy(factor=1.0, min_timeout=5.0, baseline_duration=0.0)


# ── run_parallel: ParallelRunError on result count mismatch ──────────────────


@pytest.mark.unit
def test_run_parallel_short_result_raises(tmp_path, monkeypatch):
    """_MUTATE4PY_TEST_WORKER_SHORT_RESULT=1 drops one result → ParallelRunError."""
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root, required: None)
    monkeypatch.setattr(workers_mod, "_link_import_root", lambda worker_root, package_dir: worker_root + "-import")
    monkeypatch.setenv("_MUTATE4PY_TEST_WORKER_SHORT_RESULT", "1")

    src = "def f(a, b):\n    return a > b\ndef g(a, b):\n    return a < b\n"
    sites = discover_sites(src)
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)

    with pytest.raises(ParallelRunError, match="mutation workers stopped"):
        run_parallel(
            ParallelRunRequest(
                selected_sites=sites,
                clean_source=src,
                source_path=str(src_file),
                cwd=str(tmp_path),
                pytest_args=[],
                timeout_policy=_FIVE_SECOND_POLICY,
                max_workers=2,
                on_result=noop_on_result,
                executor=FakeExecutor("survived"),
            )
        )


# ── run_parallel: narrowing composes with Worker dispatch (issue 04b) ────────


class _FakeTestContextDB:
    def __init__(self, outcome: str, node_ids: tuple = ()) -> None:
        self._result = (outcome, list(node_ids))

    def tests_for_line(self, source_path, line):
        return self._result


@pytest.mark.unit
def test_run_parallel_composes_narrowed_dispatch_with_workers(tmp_path, monkeypatch):
    """A test-context db in play must reach each Worker's dispatch args, not
    just the serial loop's — the old parallel engine never built a Mutant's
    dispatch args at all."""
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root, required: None)
    monkeypatch.setattr(workers_mod, "_link_import_root", lambda worker_root, package_dir: worker_root + "-import")

    src = "def f(a, b):\n    return a > b\ndef g(a, b):\n    return a < b\n"
    sites = discover_sites(src)
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    executor = FakeExecutor("killed")

    counts, survivors, selection_counts = run_parallel(
        ParallelRunRequest(
            selected_sites=sites,
            clean_source=src,
            source_path=str(src_file),
            cwd=str(tmp_path),
            pytest_args=["-q"],
            timeout_policy=_FIVE_SECOND_POLICY,
            max_workers=2,
            on_result=noop_on_result,
            test_ctx_db=_FakeTestContextDB("narrowed", ("tests/test_calc.py::test_f",)),
            abs_source_path=str(src_file),
            executor=executor,
        )
    )
    assert counts == {"killed": 2, "timeout": 0, "survived": 0}
    assert survivors == []
    assert selection_counts == {"narrowed": 2, "static": 0, "degraded": 0}
    assert executor.calls == [["-q", "tests/test_calc.py::test_f"]] * 2


@pytest.mark.unit
def test_run_parallel_composes_static_dispatch_with_workers(tmp_path, monkeypatch):
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root, required: None)
    monkeypatch.setattr(workers_mod, "_link_import_root", lambda worker_root, package_dir: worker_root + "-import")

    src = "def f(a, b):\n    return a > b\ndef g(a, b):\n    return a < b\n"
    sites = discover_sites(src)
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    executor = FakeExecutor("killed")

    _, _, selection_counts = run_parallel(
        ParallelRunRequest(
            selected_sites=sites,
            clean_source=src,
            source_path=str(src_file),
            cwd=str(tmp_path),
            pytest_args=["-q"],
            timeout_policy=_FIVE_SECOND_POLICY,
            max_workers=2,
            on_result=noop_on_result,
            test_ctx_db=_FakeTestContextDB("static"),
            abs_source_path=str(src_file),
            executor=executor,
        )
    )
    assert selection_counts == {"narrowed": 0, "static": 2, "degraded": 0}
    assert executor.calls == [["-q"]] * 2


@pytest.mark.unit
def test_run_parallel_composes_degraded_dispatch_with_workers(tmp_path, monkeypatch):
    """An under-listed line (issue #69) must reach every Worker's tally as
    "degraded", not "narrowed" -- the parallel engine plans each Site with the
    same plan_mutant the serial loop uses."""
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root, required: None)
    monkeypatch.setattr(workers_mod, "_link_import_root", lambda worker_root, package_dir: worker_root + "-import")

    src = "def f(a, b):\n    return a > b\ndef g(a, b):\n    return a < b\n"
    sites = discover_sites(src)
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    executor = FakeExecutor("killed")

    _, _, selection_counts = run_parallel(
        ParallelRunRequest(
            selected_sites=sites,
            clean_source=src,
            source_path=str(src_file),
            cwd=str(tmp_path),
            pytest_args=["-q"],
            timeout_policy=_FIVE_SECOND_POLICY,
            max_workers=2,
            on_result=noop_on_result,
            test_ctx_db=_FakeTestContextDB("under-listed", ("tests/test_calc.py::test_f",)),
            abs_source_path=str(src_file),
            executor=executor,
        )
    )
    assert selection_counts == {"narrowed": 0, "static": 0, "degraded": 2}
    assert executor.calls == [["-q"]] * 2


@pytest.mark.unit
def test_run_parallel_disagreement_aborts_before_any_worker_is_provisioned(tmp_path, monkeypatch):
    """Sites are planned before dispatch, so a test-context db disagreement
    aborts the parallel run before any Worker is provisioned or dispatched."""
    import mutate4py._workers as workers_mod

    provisioned: list[str] = []
    monkeypatch.setattr(
        workers_mod,
        "_provision_workers",
        lambda run_root, n_workers, real_cwd: provisioned.append(run_root) or [],
    )

    src = "def f(a, b):\n    return a > b\ndef g(a, b):\n    return a < b\n"
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    executor = FakeExecutor("killed")

    with pytest.raises(SelectionError):
        run_parallel(
            ParallelRunRequest(
                selected_sites=discover_sites(src),
                clean_source=src,
                source_path=str(src_file),
                cwd=str(tmp_path),
                pytest_args=["-q"],
                timeout_policy=_FIVE_SECOND_POLICY,
                max_workers=2,
                on_result=noop_on_result,
                test_ctx_db=_FakeTestContextDB("line-absent"),
                abs_source_path=str(src_file),
                executor=executor,
            )
        )
    assert provisioned == []
    assert executor.calls == []
    assert src_file.read_text() == src


# ── run_parallel: one Worker is primed once and serves every assigned site ───


@pytest.mark.unit
def test_run_parallel_primes_worker_executor_once_for_multiple_sites(tmp_path, monkeypatch):
    """max_workers=1 keeps everything in one Worker/one thread, so prime()
    and run() call counts are deterministic without reasoning about
    thread-interleaving across multiple Worker groups."""
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root, required: None)
    monkeypatch.setattr(workers_mod, "_link_import_root", lambda worker_root, package_dir: worker_root + "-import")

    src = "def f(a, b):\n    return a > b\ndef g(a, b):\n    return a < b\ndef h(a, b):\n    return a >= b\n"
    sites = discover_sites(src)
    assert len(sites) == 3
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    executor = FakeExecutor("survived")

    counts, _, _ = run_parallel(
        ParallelRunRequest(
            selected_sites=sites,
            clean_source=src,
            source_path=str(src_file),
            cwd=str(tmp_path),
            pytest_args=[],
            timeout_policy=_FIVE_SECOND_POLICY,
            max_workers=1,
            on_result=noop_on_result,
            executor=executor,
        )
    )
    assert counts == {"killed": 0, "timeout": 0, "survived": 3}
    assert executor.prime_calls == 1
    assert len(executor.calls) == 3


@pytest.mark.unit
def test_run_parallel_shared_injected_executor_primed_per_worker_thread(tmp_path, monkeypatch):
    """A single injected fake executor handed to multiple Worker threads
    (max_workers>=2) is primed once per Worker thread that uses it, and
    every site still gets exactly one run() call — the per-thread .prime()
    calls race on the same instance but must not lose or duplicate results."""
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root, required: None)
    monkeypatch.setattr(workers_mod, "_link_import_root", lambda worker_root, package_dir: worker_root + "-import")

    src = (
        "def f(a, b):\n    return a > b\n"
        "def g(a, b):\n    return a < b\n"
        "def h(a, b):\n    return a >= b\n"
        "def k(a, b):\n    return a <= b\n"
    )
    sites = discover_sites(src)
    assert len(sites) == 4
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    executor = FakeExecutor("survived")

    counts, _, _ = run_parallel(
        ParallelRunRequest(
            selected_sites=sites,
            clean_source=src,
            source_path=str(src_file),
            cwd=str(tmp_path),
            pytest_args=[],
            timeout_policy=_FIVE_SECOND_POLICY,
            max_workers=2,
            on_result=noop_on_result,
            executor=executor,
        )
    )
    assert counts == {"killed": 0, "timeout": 0, "survived": 4}
    assert executor.prime_calls == 2
    assert len(executor.calls) == 4


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _outcome_lines(stdout: str) -> list[str]:
    return [ln.strip() for ln in stdout.splitlines() if ln.strip().startswith(("Killed:", "Survived:"))]


@pytest.mark.integration
def test_parallel_dogfood_run_scores_the_same_as_the_serial_run(tmp_path):
    """C1: mutate4py mutating its own source must score the same under workers as serially.
    The Worker copy's mutate4py has to be the one imported; an import root on PYTHONPATH
    would resolve to the unmutated original, and every Mutant would survive."""
    project = tmp_path / "project"
    project.mkdir()
    for name in ("pyproject.toml", "uv.lock", ".python-version", "README.md", "LICENSE"):
        shutil.copy2(os.path.join(REPO_ROOT, name), project / name)
    for name in ("src", "tests", "scripts"):
        shutil.copytree(os.path.join(REPO_ROOT, name), project / name, ignore=shutil.ignore_patterns(*_SKIP_ENTRIES))
    env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "PYTHONPATH")}
    subprocess.run(["uv", "sync"], cwd=project, env=env, capture_output=True, text=True, check=True)
    subprocess.run(
        ["uv", "run", "pytest", "--cov=src", "--cov-report=lcov:lcov.info", "tests/test_cmd.py"],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    base = [
        "uv",
        "run",
        "mutate4py",
        "src/mutate4py/_cmd.py",
        "--mutate-all",
        "--lcov",
        "lcov.info",
        "--pytest-args",
        "tests/test_cmd.py",
    ]
    serial = subprocess.run(base, cwd=project, env=env, capture_output=True, text=True)
    parallel = subprocess.run(base + ["--max-workers", "2"], cwd=project, env=env, capture_output=True, text=True)
    serial_lines = _outcome_lines(serial.stdout)
    assert any(ln.startswith("Killed:") for ln in serial_lines), serial.stdout + serial.stderr
    assert any(ln.startswith("Survived:") for ln in serial_lines), serial.stdout + serial.stderr
    assert _outcome_lines(parallel.stdout) == serial_lines, parallel.stdout + parallel.stderr
    assert not any(ln == "Killed: 0" for ln in serial_lines)
