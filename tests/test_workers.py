"""Unit tests for _workers.py internals."""

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


def test_run_one_site_survived(tmp_path, monkeypatch):
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "run_argv", lambda argv, cwd, timeout: "survived")
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
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "run_argv", lambda argv, cwd, timeout: "killed")
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
    monkeypatch.setattr(workers_mod, "run_argv", lambda argv, cwd, timeout: "survived")
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
            )
        )
