"""Parallel worker engine (F6 --max-workers >= 2, sites >= 2; re-scoped by
issue 04b).

Each Worker is an isolated tree copy of the working directory with its own
uv venv (ADR 0015, unchanged). What changed: each Worker now also provisions
and owns exactly one primed Executor — the forking executor when eligible,
the subprocess executor otherwise — chosen by that Worker's own subprocess
(`_worker_server.py`) at startup and held for the Worker's whole run, so a
Mutant is dispatched over `_worker_protocol`'s request/response pipe instead
of spawning a fresh `pytest` process per Mutant. Per-site test-context
narrowing (`_test_dispatch._build_mutant_args`) now composes with parallel
Workers the same way it already does with the serial loop.
"""

import dataclasses
import os
import shutil
import subprocess
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from mutate4py._discovery import Site, apply_mutant
from mutate4py._executor import Executor
from mutate4py._test_dispatch import _build_mutant_args
from mutate4py._worker_protocol import WorkerProcessError, WorkerProcessExecutor

__all__ = ["ParallelRunError", "ParallelRunRequest", "WorkerFailureError", "run_parallel"]


@dataclasses.dataclass
class SiteAssignment:
    """One (site, worker) pairing plus its position in the overall progress count."""

    worker_idx: int
    site: Site
    site_idx: int
    total: int
    worker_root: str
    worker_file_path: str


@dataclasses.dataclass
class WorkerRunSettings:
    """Shared across every mutant run within one parallel dispatch."""

    clean_source: str
    pytest_args: list[str]
    mutant_timeout: float
    on_result: Callable
    test_ctx_db: object = None
    abs_source_path: str = ""


@dataclasses.dataclass
class ParallelRunRequest:
    selected_sites: list[Site]
    clean_source: str
    source_path: str
    cwd: str
    pytest_args: list[str]
    mutant_timeout: float
    max_workers: int
    on_result: Callable
    test_ctx_db: object = None
    abs_source_path: str = ""
    forking_requested: bool = True
    # Test-injection seam (issue 04b): when set, every Worker shares this one
    # Executor instead of provisioning a real WorkerProcessExecutor — makes
    # narrowed/static dispatch, per-Worker Site assignment, and
    # primed-once-serves-many assertable without forking or spawning anything.
    executor: Executor | None = None


@dataclasses.dataclass
class _WorkerDispatchPlan:
    """Everything one call to _dispatch_worker_groups needs, bundled to keep
    that call under ruff's positional-argument ceiling."""

    by_worker: dict[int, list[tuple[int, Site, int]]]
    worker_roots: list[str]
    executors: list[Executor]
    source_rel: str
    total: int
    settings: WorkerRunSettings
    n_workers: int


_SKIP_ENTRIES = {
    ".git",
    "__pycache__",
    ".venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".mutate4py",
}


class ParallelRunError(Exception):
    pass


class WorkerFailureError(ParallelRunError):
    pass


def _copy_tree(src_dir: str, dst_dir: str) -> None:
    """Copy src_dir to dst_dir, skipping _SKIP_ENTRIES at any level."""
    os.makedirs(dst_dir, exist_ok=True)
    for entry in os.scandir(src_dir):
        if entry.name in _SKIP_ENTRIES:
            continue
        dst = os.path.join(dst_dir, entry.name)
        if entry.is_dir(follow_symlinks=False):
            _copy_tree(entry.path, dst)
        else:
            shutil.copy2(entry.path, dst)


def _provision_worker(worker_root: str) -> None:
    """Run uv venv + uv sync to provision a worker copy."""
    subprocess.run(
        ["uv", "venv"],
        cwd=worker_root,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["uv", "sync"],
        cwd=worker_root,
        capture_output=True,
        check=True,
    )


def _provision_worker_executors(
    worker_roots: list[str],
    source_rel: str,
    *,
    forking_requested: bool,
    injected_executor: Executor | None,
) -> list[Executor]:
    """One Executor per worker root: the shared injected fake when supplied
    (tests), a real per-Worker subprocess proxy otherwise."""
    if injected_executor is not None:
        return [injected_executor for _ in worker_roots]
    return [
        WorkerProcessExecutor(
            worker_root=root,
            guarded_path=os.path.join(root, source_rel),
            forking_requested=forking_requested,
        )
        for root in worker_roots
    ]


def _run_one_site(assignment: SiteAssignment, executor: Executor, settings: WorkerRunSettings) -> dict:
    """Build this site's dispatch args, mutate the worker copy, dispatch to
    executor.run(), restore, call on_result, return the result dict."""
    args, selection = _build_mutant_args(
        settings.pytest_args, settings.test_ctx_db, settings.abs_source_path, assignment.site
    )

    with open(assignment.worker_file_path) as f:
        original_source = f.read()

    mutated = apply_mutant(settings.clean_source, assignment.site)
    if os.environ.get("_MUTATE4PY_TEST_WORKER_WRITE_FAIL") == "1":
        raise WorkerFailureError(f"worker-{assignment.worker_idx} could not write file copy: injected test failure")
    try:
        with open(assignment.worker_file_path, "w") as f:
            f.write(mutated)
    except OSError as e:
        raise WorkerFailureError(f"worker-{assignment.worker_idx} could not write file copy: {e}") from e

    try:
        status = executor.run(args, settings.mutant_timeout)
    except WorkerProcessError as e:
        raise WorkerFailureError(f"worker-{assignment.worker_idx} process failed: {e}") from e
    finally:
        try:
            with open(assignment.worker_file_path, "w") as f:
                f.write(original_source)
        except OSError as e:
            raise WorkerFailureError(f"worker-{assignment.worker_idx} could not restore file copy: {e}") from e

    result = {
        "worker_idx": assignment.worker_idx,
        "site": assignment.site,
        "site_idx": assignment.site_idx,
        "total": assignment.total,
        "status": status,
        "selection": selection,
    }
    settings.on_result(result)
    return result


def _provision_workers(run_root: str, n_workers: int, real_cwd: str) -> list[str]:
    """Create and provision n_workers isolated tree copies; return their root paths."""
    worker_roots = []
    for k in range(1, n_workers + 1):
        worker_root = os.path.join(run_root, f"worker-{k}")
        _copy_tree(real_cwd, worker_root)
        _provision_worker(worker_root)
        worker_roots.append(worker_root)
    return worker_roots


def _assign_sites_to_workers(selected_sites: list[Site], n_workers: int) -> dict[int, list[tuple[int, Site, int]]]:
    """Round-robin assign sites to workers; return by_worker grouping."""
    by_worker: dict[int, list[tuple[int, Site, int]]] = defaultdict(list)
    for i, site in enumerate(selected_sites):
        worker_idx = (site.index % n_workers) + 1
        by_worker[worker_idx].append((worker_idx, site, i + 1))
    return by_worker


def _summarize_results(results: list[dict]) -> tuple[dict[str, int], list[Site]]:
    """Tally counts and collect survivors from sorted result list."""
    counts: dict[str, int] = {"killed": 0, "timeout": 0, "survived": 0}
    survivors: list[Site] = []
    for r in results:
        counts[r["status"]] += 1
        if r["status"] == "survived":
            survivors.append(r["site"])
    survivors.sort(key=lambda s: s.index)
    return counts, survivors


def _summarize_selection(results: list[dict]) -> dict[str, int]:
    """Tally narrowed/static selection counts, mirroring the serial loop's tally."""
    counts = {"narrowed": 0, "static": 0}
    for r in results:
        selection = r.get("selection")
        if selection is not None:
            counts[selection] += 1
    return counts


def _dispatch_worker_groups(plan: _WorkerDispatchPlan) -> list[dict]:
    """Prime each Worker's executor once, run its whole assignment
    sequentially (same file path), then close it — the executor is alive
    from priming to the end of that Worker's share of the run. Workers
    dispatch across plan.n_workers threads."""
    short_fail = os.environ.get("_MUTATE4PY_TEST_WORKER_SHORT_RESULT") == "1"

    def _run_worker_group(worker_idx: int, assignments: list[tuple[int, Site, int]]) -> list[dict]:
        executor = plan.executors[worker_idx - 1]
        worker_root = plan.worker_roots[worker_idx - 1]
        worker_file_path = os.path.join(worker_root, plan.source_rel)
        try:
            executor.prime()
        except WorkerProcessError as e:
            raise WorkerFailureError(f"worker-{worker_idx} could not start: {e}") from e
        try:
            worker_results = [
                _run_one_site(
                    SiteAssignment(
                        worker_idx=worker_idx,
                        site=site,
                        site_idx=site_idx,
                        total=plan.total,
                        worker_root=worker_root,
                        worker_file_path=worker_file_path,
                    ),
                    executor,
                    plan.settings,
                )
                for (_, site, site_idx) in assignments
            ]
        finally:
            close = getattr(executor, "close", None)
            if close is not None:
                close()
        if short_fail and worker_results:
            worker_results.pop()
        return worker_results

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=plan.n_workers) as executor_pool:
        futures = {
            executor_pool.submit(_run_worker_group, worker_idx, assignments): worker_idx
            for worker_idx, assignments in plan.by_worker.items()
        }
        for future in as_completed(futures):
            results.extend(future.result())
    return results


def run_parallel(request: ParallelRunRequest) -> tuple[dict, list[Site], dict[str, int] | None]:
    """Run sites in parallel across max_workers isolated Workers, each owning
    exactly one primed Executor for the whole run.

    on_result(result_dict) is called from worker threads as each site finishes —
    callers use this to print progress lines in arrival order.

    Returns (counts, survivors, selection_counts) sorted by stable site index;
    selection_counts is None unless a test-context db is in play.
    Raises WorkerFailureError on write/restore/dispatch failure.
    Raises ParallelRunError if collected results != selected site count.
    A TestSelectionError from a disagreement (case 3) propagates uncaught.
    """
    real_source = os.path.realpath(request.source_path)
    real_cwd = os.path.realpath(request.cwd)
    if not real_source.startswith(real_cwd + os.sep):
        raise ParallelRunError(f"target file must be inside working directory: {request.source_path}")

    selected_sites = request.selected_sites
    n_workers = min(request.max_workers, len(selected_sites))
    source_rel = os.path.relpath(real_source, real_cwd)
    run_root = os.path.join(real_cwd, ".mutate4py", "workers", f"run-{os.getpid()}-{time.monotonic_ns()}")

    settings = WorkerRunSettings(
        clean_source=request.clean_source,
        pytest_args=request.pytest_args,
        mutant_timeout=request.mutant_timeout,
        on_result=request.on_result,
        test_ctx_db=request.test_ctx_db,
        abs_source_path=request.abs_source_path,
    )

    try:
        worker_roots = _provision_workers(run_root, n_workers, real_cwd)
        by_worker = _assign_sites_to_workers(selected_sites, n_workers)
        executors = _provision_worker_executors(
            worker_roots,
            source_rel,
            forking_requested=request.forking_requested,
            injected_executor=request.executor,
        )
        results = _dispatch_worker_groups(
            _WorkerDispatchPlan(
                by_worker=by_worker,
                worker_roots=worker_roots,
                executors=executors,
                source_rel=source_rel,
                total=len(selected_sites),
                settings=settings,
                n_workers=n_workers,
            )
        )

        if len(results) != len(selected_sites):
            raise ParallelRunError(f"mutation workers stopped after {len(results)}/{len(selected_sites)} results")

        results.sort(key=lambda r: r["site_idx"])
        counts, survivors = _summarize_results(results)
        selection_counts = _summarize_selection(results) if request.test_ctx_db is not None else None
        return counts, survivors, selection_counts

    finally:
        shutil.rmtree(run_root, ignore_errors=True)
