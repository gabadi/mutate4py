"""Unit tests for _workers.py internals."""

import io
import json
import os
import subprocess
import sys
import types

import pytest

from mutate4py._discovery import Site, discover_sites
from mutate4py._executor import ExecutorDescription
from mutate4py._test_dispatch import MutantPlan, NoTestsCollectedError
from mutate4py._worker_protocol import ServerLaunch, WorkerProcessError, check_worker_python
from mutate4py._worker_provision import _copy_tree, _link_import_root
from mutate4py._workers import (
    SiteAssignment,
    WorkerFailureError,
    WorkerRunSettings,
    _assign_sites_to_workers,
    _close_worker_executor,
    _drop_one_result_if_injected,
    _prime_worker_executor,
    _provision_worker,
    _provision_workers,
    _run_one_site,
    _summarize_results,
)

from ._worker_fakes_helpers import FakeExecutor, noop_on_result


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

    def describe(self) -> ExecutorDescription:  # pragma: no cover - not exercised by the lifecycle tests
        return ExecutorDescription(mode="subprocess", reason="--no-fork")


class _NoCloseExecutor:
    """An `Executor` with no close(), like the injected test executor."""

    def prime(self):  # pragma: no cover - not exercised by the close tests
        pass

    def describe(self) -> ExecutorDescription:  # pragma: no cover - not exercised by the close tests
        return ExecutorDescription(mode="subprocess", reason="--no-fork")


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
def test_copy_tree_symlink_to_file_is_recreated(tmp_path):
    """a symlink to a file is recreated as a symlink in the copy, not followed, so it still resolves."""
    src = tmp_path / "src"
    target = tmp_path / "real.txt"
    target.write_text("contents")
    src.mkdir()
    (src / "link.txt").symlink_to(target)
    (src / "a.py").write_text("x = 1")
    dst = tmp_path / "dst"
    _copy_tree(str(src), str(dst))
    assert (dst / "a.py").exists()
    assert (dst / "link.txt").is_symlink()


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
        injected_executor=None,
        source_root="/tmp/project",
        launch=ServerLaunch(forking_requested=True),
    )
    assert [e.launch.worker_id for e in executors] == ["gw1", "gw2", "gw3"]
    assert len({e.launch.worker_id for e in executors}) == 3


@pytest.mark.unit
def test_provision_worker_executors_injected_fake_ignores_worker_id():
    from mutate4py._workers import _provision_worker_executors

    fake = FakeExecutor("survived")
    executors = _provision_worker_executors(
        ["/tmp/worker-1", "/tmp/worker-2"],
        "calc.py",
        injected_executor=fake,
        source_root="/tmp/project",
        launch=ServerLaunch(forking_requested=True),
    )
    assert executors == [fake, fake]


def _ready_popen(monkeypatch) -> list:
    """Replace Popen with a recorder that answers the ready handshake."""
    launches: list = []

    def fake(argv, **kwargs):
        launches.append((argv, kwargs))
        return types.SimpleNamespace(stdin=io.StringIO(), stdout=io.StringIO(json.dumps({"ready": True}) + "\n"))

    monkeypatch.setattr(subprocess, "Popen", fake)
    # The pytest probe is its own subprocess; these tests cover the launch only.
    monkeypatch.setattr("mutate4py._worker_protocol.check_worker_pytest", lambda root: None)
    return launches


@pytest.mark.unit
def test_provision_worker_executors_primes_each_real_worker_under_its_venv(tmp_path, monkeypatch):
    from mutate4py._workers import _provision_worker_executors

    launches = _ready_popen(monkeypatch)
    monkeypatch.delenv("PYTHONPATH", raising=False)
    worker_root = str(tmp_path / "worker-1")
    (executor,) = _provision_worker_executors(
        [worker_root],
        "calc.py",
        injected_executor=None,
        source_root=str(tmp_path),
        launch=ServerLaunch(forking_requested=True),
    )
    executor.prime()
    argv, kwargs = launches[0]
    assert argv[0] == os.path.join(worker_root, ".venv", "bin", "python")
    assert "PYTHONPATH" not in kwargs["env"]


@pytest.mark.unit
def test_provision_worker_executors_primes_each_real_worker_with_the_runs_plugin_blocks(tmp_path, monkeypatch):
    from mutate4py._workers import _provision_worker_executors

    launches = _ready_popen(monkeypatch)
    (executor,) = _provision_worker_executors(
        [str(tmp_path / "worker-1")],
        "calc.py",
        injected_executor=None,
        source_root=str(tmp_path),
        launch=ServerLaunch(forking_requested=True, prime_args=("-p", "no:tach")),
    )
    executor.prime()
    argv, _ = launches[0]
    assert argv[-2:] == ["-p", "no:tach"]


# ── worker interpreter and import root ────────────────────────────────────────


def _fake_purelib_probe(monkeypatch, purelib) -> list:
    """Answer the Worker venv's purelib probe (`sysconfig.get_path('purelib')`) with `purelib`."""
    probes: list = []
    os.makedirs(purelib, exist_ok=True)

    def fake(argv, **kwargs):
        probes.append(argv)
        return types.SimpleNamespace(stdout=f"{purelib}\n", returncode=0)

    monkeypatch.setattr(subprocess, "run", fake)
    return probes


@pytest.mark.unit
def test_link_import_root_links_the_package_outside_the_worker_tree(tmp_path, monkeypatch):
    worker_root = tmp_path / "run" / "worker-1"
    worker_root.mkdir(parents=True)
    package_dir = tmp_path / "src" / "mutate4py"
    package_dir.mkdir(parents=True)
    _fake_purelib_probe(monkeypatch, tmp_path / "site-packages")

    import_root = _link_import_root(str(worker_root), str(package_dir))

    assert import_root == str(tmp_path / "run" / "worker-1-import")
    assert os.readlink(os.path.join(import_root, "mutate4py")) == str(package_dir)
    assert not os.path.realpath(import_root).startswith(str(worker_root.resolve()) + os.sep)
    assert not os.path.lexists(worker_root / "mutate4py")


@pytest.mark.unit
def test_link_import_root_writes_a_pth_file_into_the_worker_venv_after_its_own_entries(tmp_path, monkeypatch):
    """The import root is a `.pth` in the Worker venv's purelib, probed under the Worker's
    own interpreter. The name sorts after the editable install's `_<name>.pth`, so the
    project's own mutate4py wins when both exist (ADR 0015, dogfood)."""
    worker_root = tmp_path / "run" / "worker-1"
    worker_root.mkdir(parents=True)
    package_dir = tmp_path / "src" / "mutate4py"
    package_dir.mkdir(parents=True)
    purelib = tmp_path / "worker-venv-site-packages"
    probes = _fake_purelib_probe(monkeypatch, purelib)

    import_root = _link_import_root(str(worker_root), str(package_dir))

    assert probes[0][0] == os.path.join(str(worker_root), ".venv", "bin", "python")
    assert (purelib / "zzz_mutate4py_import_root.pth").read_text() == import_root + "\n"
    assert not os.path.lexists(worker_root / "mutate4py")


def _fake_worker_interpreter(worker_root, version: str) -> None:
    """A stand-in .venv/bin/python that answers the version probe with `version`."""
    bin_dir = os.path.join(str(worker_root), ".venv", "bin")
    os.makedirs(bin_dir)
    script = os.path.join(bin_dir, "python")
    with open(script, "w") as f:
        f.write(f"#!/bin/sh\necho {version}\n")
    os.chmod(script, 0o755)


@pytest.mark.unit
def test_check_worker_python_refuses_an_interpreter_below_the_3_11_floor(tmp_path):
    _fake_worker_interpreter(tmp_path, "3.9")
    with pytest.raises(WorkerProcessError) as exc:
        check_worker_python(str(tmp_path))
    assert "3.9" in str(exc.value)
    assert "3.11" in str(exc.value)


@pytest.mark.unit
def test_check_worker_python_accepts_the_3_11_floor(tmp_path):
    _fake_worker_interpreter(tmp_path, "3.11")
    check_worker_python(str(tmp_path))


@pytest.mark.unit
def test_check_worker_python_reports_a_missing_worker_interpreter(tmp_path):
    with pytest.raises(WorkerProcessError, match="no usable interpreter"):
        check_worker_python(str(tmp_path))


@pytest.mark.unit
def test_provision_worker_turns_a_below_floor_interpreter_into_a_worker_failure(tmp_path, monkeypatch):
    real_run = subprocess.run
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kwargs: None if cmd[0] == "uv" else real_run(cmd, **kwargs))
    _fake_worker_interpreter(tmp_path, "3.9")
    with pytest.raises(WorkerFailureError, match="runs Python 3.9"):
        _provision_worker(str(tmp_path), frozenset())


@pytest.mark.component
def test_provision_worker_maps_a_failed_uv_step_to_a_worker_failure_with_its_stderr_tail(tmp_path, monkeypatch):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv = fake_bin / "uv"
    uv.write_text('#!/bin/sh\nif [ "$1" = "sync" ]; then echo "error: no solution found" >&2; exit 2; fi\nexit 0\n')
    uv.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}{os.pathsep}{os.environ['PATH']}")
    worker_root = tmp_path / "worker-1"
    worker_root.mkdir()

    with pytest.raises(WorkerFailureError, match="uv sync .* failed") as exc:
        _provision_worker(str(worker_root), frozenset())
    assert "error: no solution found" in str(exc.value)
    assert isinstance(exc.value.__cause__, subprocess.CalledProcessError)


@pytest.mark.component
def test_provision_worker_maps_a_missing_uv_to_a_worker_failure(tmp_path, monkeypatch):
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))
    worker_root = tmp_path / "worker-1"
    worker_root.mkdir()

    with pytest.raises(WorkerFailureError, match="could not run uv") as exc:
        _provision_worker(str(worker_root), frozenset())
    assert isinstance(exc.value.__cause__, OSError)


@pytest.mark.unit
def test_provision_workers_restates_an_import_root_link_failure_as_a_worker_failure(tmp_path, monkeypatch):
    import mutate4py._workers as workers_mod

    monkeypatch.setattr(workers_mod, "_copy_tree", lambda src, dst: os.makedirs(dst))
    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root, required: None)

    def refuse_symlink(src, dst, *args, **kwargs):
        raise OSError("symlinks refused")

    monkeypatch.setattr(os, "symlink", refuse_symlink)
    with pytest.raises(WorkerFailureError, match="could not link the mutate4py import root") as exc:
        _provision_workers(str(tmp_path / "run"), 1, str(tmp_path / "project"))
    assert isinstance(exc.value.__cause__, OSError)


@pytest.mark.unit
def test_prime_worker_executor_reports_a_missing_worker_interpreter_as_a_worker_failure(tmp_path):
    from mutate4py._worker_protocol import WorkerProcessExecutor

    executor = WorkerProcessExecutor(
        worker_root=str(tmp_path),
        guarded_path=str(tmp_path / "calc.py"),
        source_root=str(tmp_path),
        launch=ServerLaunch(forking_requested=True),
    )
    with pytest.raises(WorkerFailureError, match="worker-2 could not start") as exc:
        _prime_worker_executor(executor, 2)
    assert isinstance(exc.value.__cause__, WorkerProcessError)


@pytest.mark.component
def test_prime_worker_executor_refuses_a_worker_venv_without_pytest(tmp_path):
    """A Worker venv that cannot import pytest exits 1 on every Mutant, which would
    read as killed. Priming refuses it as a Worker failure, before any dispatch."""
    from mutate4py._worker_protocol import WorkerProcessExecutor

    worker_root = tmp_path / "worker-1"
    worker_root.mkdir()
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(worker_root / ".venv")], check=True)
    executor = WorkerProcessExecutor(
        worker_root=str(worker_root),
        guarded_path=str(worker_root / "calc.py"),
        source_root=str(tmp_path),
        launch=ServerLaunch(forking_requested=True),
    )
    with pytest.raises(WorkerFailureError, match="has no pytest") as exc:
        _prime_worker_executor(executor, 1)
    assert f"worker environment {worker_root} has no pytest" in str(exc.value)
    assert "`uv sync` installs it" in str(exc.value)


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
            plan=MutantPlan(args=[], timeout=5.0, selection=None),
        ),
        FakeExecutor("survived"),
        WorkerRunSettings(
            clean_source=src,
            on_result=noop_on_result,
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
            plan=MutantPlan(args=[], timeout=5.0, selection=None),
        ),
        FakeExecutor("killed"),
        WorkerRunSettings(
            clean_source=src,
            on_result=noop_on_result,
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
                plan=MutantPlan(args=[], timeout=5.0, selection=None),
            ),
            FakeExecutor(status),
            WorkerRunSettings(
                clean_source=src,
                on_result=noop_on_result,
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
                plan=MutantPlan(args=[], timeout=5.0, selection=None),
            ),
            FakeExecutor("survived"),
            WorkerRunSettings(
                clean_source=src,
                on_result=noop_on_result,
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
                plan=MutantPlan(args=[], timeout=5.0, selection=None),
            ),
            FakeExecutor("survived"),
            WorkerRunSettings(
                clean_source=src,
                on_result=noop_on_result,
            ),
        )


class _TimedFakeExecutor:
    """Records each dispatch's (args, timeout) so a test can see both halves of a plan."""

    def __init__(self, status: str) -> None:
        self._status = status
        self.dispatched: list[tuple[list[str], float]] = []

    def prime(self) -> None:
        pass

    def run(self, args: list[str], timeout: float) -> str:
        self.dispatched.append((list(args), timeout))
        return self._status

    def describe(self) -> ExecutorDescription:
        return ExecutorDescription(mode="subprocess", reason="--no-fork")


@pytest.mark.unit
def test_run_one_site_dispatches_the_plan_its_assignment_carries(tmp_path, monkeypatch):
    """The Worker never re-derives args or timeout: it dispatches the MutantPlan
    its SiteAssignment carries and reports that plan's selection tally."""
    src = "def f(a, b):\n    return a > b\n"
    site = discover_sites(src)[0]
    worker_file = tmp_path / "calc.py"
    worker_file.write_text(src)
    monkeypatch.delenv("_MUTATE4PY_TEST_WORKER_WRITE_FAIL", raising=False)
    executor = _TimedFakeExecutor("killed")

    result = _run_one_site(
        SiteAssignment(
            worker_idx=1,
            site=site,
            site_idx=1,
            total=1,
            worker_root=str(tmp_path),
            worker_file_path=str(worker_file),
            plan=MutantPlan(args=["-q", "tests/test_calc.py::test_f"], timeout=7.5, selection="narrowed"),
        ),
        executor,
        WorkerRunSettings(clean_source=src, on_result=noop_on_result),
    )
    assert executor.dispatched == [(["-q", "tests/test_calc.py::test_f"], 7.5)]
    assert result["selection"] == "narrowed"
    assert worker_file.read_text() == src
