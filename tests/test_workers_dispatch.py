"""Unit tests for run_parallel's dispatch: the plan's selection tally reaches each
Worker, an unrecognized selection outcome aborts before any Worker is provisioned,
executors are primed per Worker. Internals are covered in test_workers.py."""

import pytest

from mutate4py._discovery import discover_sites
from mutate4py._test_dispatch import NoTestsCollectedError, TimeoutPolicy
from mutate4py._workers import ParallelRunError, ParallelRunRequest, run_parallel

from ._worker_fakes_helpers import FakeExecutor, noop_on_result

_FIVE_SECOND_POLICY = TimeoutPolicy(factor=1.0, min_timeout=5.0, overhead=0.0, budget_of=lambda node_ids: 0.0)


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


class _FakeSelectionSource:
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
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_calc.py").write_text("def test_f():\n    assert True\n")
    executor = FakeExecutor("killed")

    result = run_parallel(
        ParallelRunRequest(
            selected_sites=sites,
            clean_source=src,
            source_path=str(src_file),
            cwd=str(tmp_path),
            pytest_args=["-q"],
            timeout_policy=_FIVE_SECOND_POLICY,
            max_workers=2,
            on_result=noop_on_result,
            selection_source=_FakeSelectionSource("narrowed", ("tests/test_calc.py::test_f",)),
            abs_source_path=str(src_file),
            executor=executor,
        )
    )
    assert result.counts == {"killed": 2, "timeout": 0, "survived": 0}
    assert result.survivors == []
    assert result.selection_counts == {"narrowed": 2, "static": 0}
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

    result = run_parallel(
        ParallelRunRequest(
            selected_sites=sites,
            clean_source=src,
            source_path=str(src_file),
            cwd=str(tmp_path),
            pytest_args=["-q"],
            timeout_policy=_FIVE_SECOND_POLICY,
            max_workers=2,
            on_result=noop_on_result,
            selection_source=_FakeSelectionSource("static"),
            abs_source_path=str(src_file),
            executor=executor,
        )
    )
    assert result.selection_counts == {"narrowed": 0, "static": 2}
    assert executor.calls == [["-q"]] * 2


@pytest.mark.unit
def test_run_parallel_unrecognized_outcome_aborts_before_any_worker_is_provisioned(tmp_path, monkeypatch):
    """Sites are planned before dispatch, so an unrecognized selection outcome
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

    with pytest.raises(ValueError, match="unrecognized selection outcome"):
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
                selection_source=_FakeSelectionSource("bogus"),
                abs_source_path=str(src_file),
                executor=executor,
            )
        )
    assert provisioned == []
    assert executor.calls == []
    assert src_file.read_text() == src


@pytest.mark.unit
def test_run_parallel_node_id_file_missing_aborts_before_any_worker_is_provisioned(tmp_path, monkeypatch):
    """A node id whose file is not under the run directory is a pytest exit 4 for every Mutant.
    The plan says so before any Worker is provisioned, whatever the Mutant timeout is."""
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

    with pytest.raises(NoTestsCollectedError, match="member/tests/test_calc.py::test_f"):
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
                selection_source=_FakeSelectionSource("narrowed", ("member/tests/test_calc.py::test_f",)),
                abs_source_path=str(src_file),
                executor=executor,
            )
        )
    assert provisioned == []
    assert executor.calls == []


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

    result = run_parallel(
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
    assert result.counts == {"killed": 0, "timeout": 0, "survived": 3}
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

    result = run_parallel(
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
    assert result.counts == {"killed": 0, "timeout": 0, "survived": 4}
    assert executor.prime_calls == 2
    assert len(executor.calls) == 4


# ── run_parallel: the result says how its Workers ran and how long Mutants took ──


@pytest.mark.unit
def test_run_parallel_reports_the_executor_description_its_workers_gave(tmp_path, monkeypatch):
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root, required: None)
    monkeypatch.setattr(workers_mod, "_link_import_root", lambda worker_root, package_dir: worker_root + "-import")

    src = "def f(a, b):\n    return a > b\ndef g(a, b):\n    return a < b\n"
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)

    result = run_parallel(
        ParallelRunRequest(
            selected_sites=discover_sites(src),
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
    assert result.executor_description.render() == "subprocess (--no-fork)"


@pytest.mark.unit
def test_run_parallel_times_each_mutant_into_the_bucket_its_status_names(tmp_path, monkeypatch):
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root, required: None)
    monkeypatch.setattr(workers_mod, "_link_import_root", lambda worker_root, package_dir: worker_root + "-import")

    src = "def f(a, b):\n    return a > b\ndef g(a, b):\n    return a < b\n"
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)

    result = run_parallel(
        ParallelRunRequest(
            selected_sites=discover_sites(src),
            clean_source=src,
            source_path=str(src_file),
            cwd=str(tmp_path),
            pytest_args=[],
            timeout_policy=_FIVE_SECOND_POLICY,
            max_workers=1,
            on_result=noop_on_result,
            executor=FakeExecutor("timeout"),
        )
    )
    assert (result.timing.timeouts_count, result.timing.mutants_count) == (2, 0)
