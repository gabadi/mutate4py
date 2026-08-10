"""Unit tests for _workers.py internals."""

import threading

import pytest

from mutate4py._discovery import Site, discover_sites
from mutate4py._workers import (
    ParallelRunError,
    ParallelRunRequest,
    SiteAssignment,
    WorkerFailureError,
    WorkerRunSettings,
    _assign_sites_to_workers,
    _copy_tree,
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


# ── _copy_tree ────────────────────────────────────────────────────────────────


def test_copy_tree_copies_files(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    (src / "a.py").write_text("hello")
    _copy_tree(str(src), str(dst))
    assert (dst / "a.py").read_text() == "hello"


def test_copy_tree_recurses_into_subdirs(tmp_path):
    src = tmp_path / "src"
    sub = src / "sub"
    dst = tmp_path / "dst"
    sub.mkdir(parents=True)
    (sub / "b.py").write_text("world")
    _copy_tree(str(src), str(dst))
    assert (dst / "sub" / "b.py").read_text() == "world"


def test_copy_tree_skips_venv(tmp_path):
    src = tmp_path / "src"
    (src / ".venv").mkdir(parents=True)
    (src / ".venv" / "pyvenv.cfg").write_text("home = /usr")
    (src / "a.py").write_text("x = 1")
    dst = tmp_path / "dst"
    _copy_tree(str(src), str(dst))
    assert not (dst / ".venv").exists()
    assert (dst / "a.py").exists()


def test_copy_tree_skips_pycache(tmp_path):
    src = tmp_path / "src"
    (src / "__pycache__").mkdir(parents=True)
    (src / "__pycache__" / "mod.cpython-312.pyc").write_text("")
    (src / "a.py").write_text("x = 1")
    dst = tmp_path / "dst"
    _copy_tree(str(src), str(dst))
    assert not (dst / "__pycache__").exists()
    assert (dst / "a.py").exists()


def test_copy_tree_skips_git(tmp_path):
    src = tmp_path / "src"
    (src / ".git").mkdir(parents=True)
    (src / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (src / "a.py").write_text("x = 1")
    dst = tmp_path / "dst"
    _copy_tree(str(src), str(dst))
    assert not (dst / ".git").exists()
    assert (dst / "a.py").exists()


def test_copy_tree_skips_mutate4py_dir(tmp_path):
    src = tmp_path / "src"
    (src / ".mutate4py").mkdir(parents=True)
    (src / ".mutate4py" / "marker").write_text("present\n")
    (src / "a.py").write_text("x = 1")
    dst = tmp_path / "dst"
    _copy_tree(str(src), str(dst))
    assert not (dst / ".mutate4py").exists()
    assert (dst / "a.py").exists()


def test_copy_tree_copies_regular_subdir(tmp_path):
    src = tmp_path / "src"
    (src / "src").mkdir(parents=True)
    (src / "src" / "module.py").write_text("x = 1")
    (src / "a.py").write_text("root = True")
    dst = tmp_path / "dst"
    _copy_tree(str(src), str(dst))
    assert (dst / "src" / "module.py").exists()
    assert (dst / "a.py").exists()


def test_copy_tree_idempotent_to_existing_dst(tmp_path):
    """_copy_tree is callable twice to same dst (exist_ok=True required)."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("x = 1")
    dst = tmp_path / "dst"
    _copy_tree(str(src), str(dst))
    _copy_tree(str(src), str(dst))
    assert (dst / "a.py").exists()


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


def test_assign_sites_round_robins():
    sites = [_make_site(i, i + 1) for i in range(4)]
    by_worker = _assign_sites_to_workers(sites, n_workers=2)
    assert set(by_worker.keys()) == {1, 2}
    total = sum(len(v) for v in by_worker.values())
    assert total == 4


# ── _summarize_results ────────────────────────────────────────────────────────


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
    assert selection_counts == {"narrowed": 2, "static": 0}
    assert executor.calls == [["-q", "tests/test_calc.py::test_f"]] * 2


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
    assert selection_counts == {"narrowed": 0, "static": 2}
    assert executor.calls == [["-q"]] * 2


# ── run_parallel: one Worker is primed once and serves every assigned site ───


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
