"""Unit tests for _workers.py internals."""

import threading

import pytest

from mutate4py._discovery import Site, discover_sites
from mutate4py._test_dispatch import NoTestsCollectedError
from mutate4py._worker_protocol import WorkerProcessError
from mutate4py._workers import (
    ParallelRunError,
    ParallelRunRequest,
    SiteAssignment,
    WorkerFailureError,
    WorkerRunSettings,
    _assign_sites_to_workers,
    _close_worker_executor,
    _copy_tree,
    _drop_one_result_if_injected,
    _prime_worker_executor,
    _run_one_site,
    _summarize_results,
    run_parallel,
)


def _make_site(index: int, line: int, fid: str = "func/f") -> Site:
    return Site(
        index=index,
        line=line,
        col=0,
        end_line=line,
        end_col=5,
        function_id=fid,
        orig_text=">",
        mutant_text=">=",
        desc="> -> >=",
    )


# ── per-Worker executor lifecycle ─────────────────────────────────────────────


class _PrimeOnlyExecutor:
    """Records prime()/close() without owning anything to dispatch to."""

    def __init__(self, *, prime_error: Exception | None = None):
        self._prime_error = prime_error
        self.calls: list[str] = []

    def prime(self):
        self.calls.append("prime")
        if self._prime_error is not None:
            raise self._prime_error

    def close(self):
        self.calls.append("close")


class _NoCloseExecutor:
    """An `Executor` with no close(), like the injected test executor."""

    def prime(self):  # pragma: no cover - not exercised by the close tests
        pass


@pytest.mark.unit
def test_prime_worker_executor_primes_once():
    executor = _PrimeOnlyExecutor()
    _prime_worker_executor(executor, 2)
    assert executor.calls == ["prime"]


@pytest.mark.unit
def test_prime_worker_executor_restates_a_protocol_failure_as_a_worker_failure():
    executor = _PrimeOnlyExecutor(prime_error=WorkerProcessError("pipe died"))
    with pytest.raises(WorkerFailureError, match="worker-2 could not start: pipe died") as exc:
        _prime_worker_executor(executor, 2)
    assert isinstance(exc.value.__cause__, WorkerProcessError)


@pytest.mark.unit
def test_close_worker_executor_closes_a_closable_executor():
    executor = _PrimeOnlyExecutor()
    _close_worker_executor(executor)
    assert executor.calls == ["close"]


@pytest.mark.unit
def test_close_worker_executor_tolerates_an_executor_without_close():
    _close_worker_executor(_NoCloseExecutor())


@pytest.mark.unit
def test_drop_one_result_if_injected_is_a_no_op_by_default():
    results = [{"site_idx": 1}, {"site_idx": 2}]
    assert _drop_one_result_if_injected(results, short_fail=False) == results


@pytest.mark.unit
def test_drop_one_result_if_injected_drops_the_last_result_when_armed():
    assert _drop_one_result_if_injected([{"site_idx": 1}, {"site_idx": 2}], short_fail=True) == [{"site_idx": 1}]


@pytest.mark.unit
def test_drop_one_result_if_injected_leaves_an_empty_group_alone():
    assert _drop_one_result_if_injected([], short_fail=True) == []


# ── _copy_tree ────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_copy_tree_copies_files(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    (src / "a.py").write_text("hello")
    _copy_tree(str(src), str(dst))
    assert (dst / "a.py").read_text() == "hello"


@pytest.mark.unit
def test_copy_tree_recurses_into_subdirs(tmp_path):
    src = tmp_path / "src"
    sub = src / "sub"
    dst = tmp_path / "dst"
    sub.mkdir(parents=True)
    (sub / "b.py").write_text("world")
    _copy_tree(str(src), str(dst))
    assert (dst / "sub" / "b.py").read_text() == "world"


@pytest.mark.unit
def test_copy_tree_skips_venv(tmp_path):
    src = tmp_path / "src"
    (src / ".venv").mkdir(parents=True)
    (src / ".venv" / "pyvenv.cfg").write_text("home = /usr")
    (src / "a.py").write_text("x = 1")
    dst = tmp_path / "dst"
    _copy_tree(str(src), str(dst))
    assert not (dst / ".venv").exists()
    assert (dst / "a.py").exists()


@pytest.mark.unit
def test_copy_tree_skips_pycache(tmp_path):
    src = tmp_path / "src"
    (src / "__pycache__").mkdir(parents=True)
    (src / "__pycache__" / "mod.cpython-312.pyc").write_text("")
    (src / "a.py").write_text("x = 1")
    dst = tmp_path / "dst"
    _copy_tree(str(src), str(dst))
    assert not (dst / "__pycache__").exists()
    assert (dst / "a.py").exists()


@pytest.mark.unit
def test_copy_tree_skips_git(tmp_path):
    src = tmp_path / "src"
    (src / ".git").mkdir(parents=True)
    (src / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (src / "a.py").write_text("x = 1")
    dst = tmp_path / "dst"
    _copy_tree(str(src), str(dst))
    assert not (dst / ".git").exists()
    assert (dst / "a.py").exists()


@pytest.mark.unit
def test_copy_tree_skips_mutate4py_dir(tmp_path):
    src = tmp_path / "src"
    (src / ".mutate4py").mkdir(parents=True)
    (src / ".mutate4py" / "marker").write_text("present\n")
    (src / "a.py").write_text("x = 1")
    dst = tmp_path / "dst"
    _copy_tree(str(src), str(dst))
    assert not (dst / ".mutate4py").exists()
    assert (dst / "a.py").exists()


@pytest.mark.unit
def test_copy_tree_copies_regular_subdir(tmp_path):
    src = tmp_path / "src"
    (src / "src").mkdir(parents=True)
    (src / "src" / "module.py").write_text("x = 1")
    (src / "a.py").write_text("root = True")
    dst = tmp_path / "dst"
    _copy_tree(str(src), str(dst))
    assert (dst / "src" / "module.py").exists()
    assert (dst / "a.py").exists()


@pytest.mark.unit
def test_copy_tree_idempotent_to_existing_dst(tmp_path):
    """_copy_tree is callable twice to same dst (exist_ok=True required)."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("x = 1")
    dst = tmp_path / "dst"
    _copy_tree(str(src), str(dst))
    _copy_tree(str(src), str(dst))
    assert (dst / "a.py").exists()


@pytest.mark.unit
def test_copy_tree_skips_all_skip_entries_copies_all_regular(tmp_path):
    """continue (not break): ALL regular files are copied even with multiple skip entries interspersed.

    With 3 regular files and 3 skip-list dirs, break would stop after the first skip,
    leaving some regular files uncopied. continue copies all regular files.
    """
    src = tmp_path / "src"
    src.mkdir()
    for skip in ["__pycache__", ".git", ".venv"]:
        (src / skip).mkdir()
        (src / skip / "dummy").write_text("")
    for name in ["a.py", "b.py", "c.py"]:
        (src / name).write_text("x = 1")
    dst = tmp_path / "dst"
    _copy_tree(str(src), str(dst))
    for skip in ["__pycache__", ".git", ".venv"]:
        assert not (dst / skip).exists(), f"Skip entry {skip} should not be copied"
    for name in ["a.py", "b.py", "c.py"]:
        assert (dst / name).exists(), f"Regular file {name} should be copied"


@pytest.mark.unit
def test_copy_tree_symlink_to_file_is_copied(tmp_path):
    """follow_symlinks=False: a symlink to a regular file is treated as a file and copied."""
    src = tmp_path / "src"
    target = tmp_path / "real.txt"
    target.write_text("contents")
    src.mkdir()
    (src / "link.txt").symlink_to(target)
    (src / "a.py").write_text("x = 1")
    dst = tmp_path / "dst"
    _copy_tree(str(src), str(dst))
    assert (dst / "a.py").exists()
    assert (dst / "link.txt").exists()


# ── _assign_sites_to_workers ──────────────────────────────────────────────────


@pytest.mark.unit
def test_assign_sites_round_robins():
    sites = [_make_site(i, i + 1) for i in range(4)]
    by_worker = _assign_sites_to_workers(sites, n_workers=2)
    assert set(by_worker.keys()) == {1, 2}
    total = sum(len(v) for v in by_worker.values())
    assert total == 4


# ── _provision_worker_executors ───────────────────────────────────────────────


@pytest.mark.unit
def test_provision_worker_executors_assigns_distinct_worker_ids():
    """Each real WorkerProcessExecutor gets its own worker_id (issue 05) —
    the identity pytest-django needs to keep per-Worker test databases from
    colliding — so worker roots must never share one. Numbered from 1 to
    match worker_roots' own "worker-1", "worker-2", ... naming and the CLI
    progress line's worker_idx, not pytest-xdist's 0-based convention."""
    from mutate4py._workers import _provision_worker_executors

    executors = _provision_worker_executors(
        ["/tmp/worker-1", "/tmp/worker-2", "/tmp/worker-3"],
        "calc.py",
        forking_requested=True,
        injected_executor=None,
    )
    assert [e._worker_id for e in executors] == ["gw1", "gw2", "gw3"]
    assert len({e._worker_id for e in executors}) == 3


@pytest.mark.unit
def test_provision_worker_executors_injected_fake_ignores_worker_id():
    from mutate4py._workers import _provision_worker_executors

    fake = _FakeExecutor("survived")
    executors = _provision_worker_executors(
        ["/tmp/worker-1", "/tmp/worker-2"],
        "calc.py",
        forking_requested=True,
        injected_executor=fake,
    )
    assert executors == [fake, fake]


# ── _summarize_results ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_summarize_results_counts_and_survivors():
    site_a = _make_site(0, 1)
    site_b = _make_site(1, 2)
    results = [
        {"status": "killed", "site": site_a},
        {"status": "survived", "site": site_b},
    ]
    counts, survivors = _summarize_results(results)
    assert counts == {"killed": 1, "timeout": 0, "survived": 1}
    assert survivors == [site_b]


@pytest.mark.unit
def test_summarize_results_timeout_tallied():
    site = _make_site(0, 1)
    results = [{"status": "timeout", "site": site}]
    counts, survivors = _summarize_results(results)
    assert counts["timeout"] == 1
    assert survivors == []


# ── _run_one_site ─────────────────────────────────────────────────────────────


def _noop_on_result(result: dict) -> None:
    pass


class _FakeExecutor:
    """Minimal stand-in for the Executor protocol: no forking, no subprocess.

    Lock-guarded so multiple Worker threads can share one instance (as
    happens when a test injects a single fake executor at max_workers>=2)
    without racing on prime_calls/calls.
    """

    def __init__(self, status: str) -> None:
        self._status = status
        self._lock = threading.Lock()
        self.calls: list[list[str]] = []
        self.prime_calls = 0

    def prime(self) -> None:
        with self._lock:
            self.prime_calls += 1

    def run(self, args: list[str], timeout: float) -> str:
        with self._lock:
            self.calls.append(args)
        return self._status


@pytest.mark.unit
def test_run_one_site_survived(tmp_path, monkeypatch):
    src = "def f(a, b):\n    return a > b\n"
    sites = discover_sites(src)
    site = sites[0]
    worker_file = tmp_path / "calc.py"
    worker_file.write_text(src)
    monkeypatch.delenv("_MUTATE4PY_TEST_WORKER_WRITE_FAIL", raising=False)

    result = _run_one_site(
        SiteAssignment(
            worker_idx=1,
            site=site,
            site_idx=1,
            total=1,
            worker_root=str(tmp_path),
            worker_file_path=str(worker_file),
        ),
        _FakeExecutor("survived"),
        WorkerRunSettings(
            clean_source=src,
            pytest_args=[],
            mutant_timeout=5.0,
            on_result=_noop_on_result,
        ),
    )
    assert result["status"] == "survived"
    assert worker_file.read_text() == src


@pytest.mark.unit
def test_run_one_site_killed(tmp_path, monkeypatch):
    src = "def f(a, b):\n    return a > b\n"
    sites = discover_sites(src)
    site = sites[0]
    worker_file = tmp_path / "calc.py"
    worker_file.write_text(src)
    monkeypatch.delenv("_MUTATE4PY_TEST_WORKER_WRITE_FAIL", raising=False)

    result = _run_one_site(
        SiteAssignment(
            worker_idx=1,
            site=site,
            site_idx=1,
            total=1,
            worker_root=str(tmp_path),
            worker_file_path=str(worker_file),
        ),
        _FakeExecutor("killed"),
        WorkerRunSettings(
            clean_source=src,
            pytest_args=[],
            mutant_timeout=5.0,
            on_result=_noop_on_result,
        ),
    )
    assert result["status"] == "killed"
    assert worker_file.read_text() == src


@pytest.mark.unit
@pytest.mark.parametrize("status, hint", [("no-tests-collected", "collected no tests"), ("usage-error", "usage error")])
def test_run_one_site_no_tests_collected_raises_and_still_restores(tmp_path, monkeypatch, status, hint):
    """A Mutant whose test run exercised no test at all must abort, not be
    tallied `killed` (issue #55) — and the worker's file copy must still be
    restored, same as a WorkerProcessError."""
    src = "def f(a, b):\n    return a > b\n"
    sites = discover_sites(src)
    site = sites[0]
    worker_file = tmp_path / "calc.py"
    worker_file.write_text(src)
    monkeypatch.delenv("_MUTATE4PY_TEST_WORKER_WRITE_FAIL", raising=False)

    with pytest.raises(NoTestsCollectedError, match=hint):
        _run_one_site(
            SiteAssignment(
                worker_idx=1,
                site=site,
                site_idx=1,
                total=1,
                worker_root=str(tmp_path),
                worker_file_path=str(worker_file),
            ),
            _FakeExecutor(status),
            WorkerRunSettings(
                clean_source=src,
                pytest_args=[],
                mutant_timeout=5.0,
                on_result=_noop_on_result,
                abs_source_path=str(worker_file),
            ),
        )
    assert worker_file.read_text() == src


@pytest.mark.unit
def test_run_one_site_write_fail_env_hook(tmp_path, monkeypatch):
    src = "def f(a, b):\n    return a > b\n"
    sites = discover_sites(src)
    worker_file = tmp_path / "calc.py"
    worker_file.write_text(src)
    monkeypatch.setenv("_MUTATE4PY_TEST_WORKER_WRITE_FAIL", "1")

    with pytest.raises(WorkerFailureError, match="injected test failure"):
        _run_one_site(
            SiteAssignment(
                worker_idx=2,
                site=sites[0],
                site_idx=1,
                total=1,
                worker_root=str(tmp_path),
                worker_file_path=str(worker_file),
            ),
            _FakeExecutor("survived"),
            WorkerRunSettings(
                clean_source=src,
                pytest_args=[],
                mutant_timeout=5.0,
                on_result=_noop_on_result,
            ),
        )


@pytest.mark.unit
def test_run_one_site_write_oserror(tmp_path, monkeypatch):
    src = "def f(a, b):\n    return a > b\n"
    sites = discover_sites(src)
    worker_file = tmp_path / "calc.py"
    worker_file.write_text(src)
    monkeypatch.delenv("_MUTATE4PY_TEST_WORKER_WRITE_FAIL", raising=False)

    call_count = [0]
    orig_open = open

    def patched_open(path, mode="r", **kw):
        if "w" in mode and str(worker_file) in str(path):
            call_count[0] += 1
            if call_count[0] == 1:
                raise OSError("disk full")
        return orig_open(path, mode, **kw)

    import builtins

    monkeypatch.setattr(builtins, "open", patched_open)

    with pytest.raises(WorkerFailureError, match="could not write file copy"):
        _run_one_site(
            SiteAssignment(
                worker_idx=1,
                site=sites[0],
                site_idx=1,
                total=1,
                worker_root=str(tmp_path),
                worker_file_path=str(worker_file),
            ),
            _FakeExecutor("survived"),
            WorkerRunSettings(
                clean_source=src,
                pytest_args=[],
                mutant_timeout=5.0,
                on_result=_noop_on_result,
            ),
        )


# ── run_parallel: ParallelRunError on result count mismatch ──────────────────


@pytest.mark.unit
def test_run_parallel_short_result_raises(tmp_path, monkeypatch):
    """_MUTATE4PY_TEST_WORKER_SHORT_RESULT=1 drops one result → ParallelRunError."""
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root: None)
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
                mutant_timeout=5.0,
                max_workers=2,
                on_result=_noop_on_result,
                executor=_FakeExecutor("survived"),
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
    just the serial loop's — the old parallel engine never called
    _build_mutant_args at all."""
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root: None)

    src = "def f(a, b):\n    return a > b\ndef g(a, b):\n    return a < b\n"
    sites = discover_sites(src)
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    executor = _FakeExecutor("killed")

    counts, survivors, selection_counts = run_parallel(
        ParallelRunRequest(
            selected_sites=sites,
            clean_source=src,
            source_path=str(src_file),
            cwd=str(tmp_path),
            pytest_args=["-q"],
            mutant_timeout=5.0,
            max_workers=2,
            on_result=_noop_on_result,
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

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root: None)

    src = "def f(a, b):\n    return a > b\ndef g(a, b):\n    return a < b\n"
    sites = discover_sites(src)
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    executor = _FakeExecutor("killed")

    _, _, selection_counts = run_parallel(
        ParallelRunRequest(
            selected_sites=sites,
            clean_source=src,
            source_path=str(src_file),
            cwd=str(tmp_path),
            pytest_args=["-q"],
            mutant_timeout=5.0,
            max_workers=2,
            on_result=_noop_on_result,
            test_ctx_db=_FakeTestContextDB("static"),
            abs_source_path=str(src_file),
            executor=executor,
        )
    )
    assert selection_counts == {"narrowed": 0, "static": 2, "degraded": 0}
    assert executor.calls == [["-q"]] * 2


def test_run_parallel_composes_degraded_dispatch_with_workers(tmp_path, monkeypatch):
    """An under-listed line (issue #69) must reach every Worker's tally as
    "degraded", not "narrowed" -- the parallel engine mirrors the serial
    loop's _build_mutant_args dispatch exactly."""
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root: None)

    src = "def f(a, b):\n    return a > b\ndef g(a, b):\n    return a < b\n"
    sites = discover_sites(src)
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    executor = _FakeExecutor("killed")

    _, _, selection_counts = run_parallel(
        ParallelRunRequest(
            selected_sites=sites,
            clean_source=src,
            source_path=str(src_file),
            cwd=str(tmp_path),
            pytest_args=["-q"],
            mutant_timeout=5.0,
            max_workers=2,
            on_result=_noop_on_result,
            test_ctx_db=_FakeTestContextDB("under-listed", ("tests/test_calc.py::test_f",)),
            abs_source_path=str(src_file),
            executor=executor,
        )
    )
    assert selection_counts == {"narrowed": 0, "static": 0, "degraded": 2}
    assert executor.calls == [["-q"]] * 2


# ── run_parallel: one Worker is primed once and serves every assigned site ───


@pytest.mark.unit
def test_run_parallel_primes_worker_executor_once_for_multiple_sites(tmp_path, monkeypatch):
    """max_workers=1 keeps everything in one Worker/one thread, so prime()
    and run() call counts are deterministic without reasoning about
    thread-interleaving across multiple Worker groups."""
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root: None)

    src = "def f(a, b):\n    return a > b\ndef g(a, b):\n    return a < b\ndef h(a, b):\n    return a >= b\n"
    sites = discover_sites(src)
    assert len(sites) == 3
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    executor = _FakeExecutor("survived")

    counts, _, _ = run_parallel(
        ParallelRunRequest(
            selected_sites=sites,
            clean_source=src,
            source_path=str(src_file),
            cwd=str(tmp_path),
            pytest_args=[],
            mutant_timeout=5.0,
            max_workers=1,
            on_result=_noop_on_result,
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

    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root: None)

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
    executor = _FakeExecutor("survived")

    counts, _, _ = run_parallel(
        ParallelRunRequest(
            selected_sites=sites,
            clean_source=src,
            source_path=str(src_file),
            cwd=str(tmp_path),
            pytest_args=[],
            mutant_timeout=5.0,
            max_workers=2,
            on_result=_noop_on_result,
            executor=executor,
        )
    )
    assert counts == {"killed": 0, "timeout": 0, "survived": 4}
    assert executor.prime_calls == 2
    assert len(executor.calls) == 4
