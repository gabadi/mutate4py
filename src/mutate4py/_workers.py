"""Parallel worker engine for F6 (--max-workers >= 2, sites >= 2).

Each worker is an isolated tree copy of the working directory, provisioned with
its own uv venv. Workers run test commands verbatim with cwd = worker root.
"""

import os
import shutil
import subprocess
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from mutate4py._cmd import run_command as _run_command
from mutate4py._discovery import Site, apply_mutant

__all__ = ["ParallelRunError", "WorkerFailureError", "run_parallel"]

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


def _run_one_site(
    worker_idx: int,
    site: Site,
    site_idx: int,
    total: int,
    clean_source: str,
    worker_root: str,
    worker_file_path: str,
    test_command: str,
    mutant_timeout: float,
    on_result: Callable,
) -> dict:
    """Mutate the worker copy, run test, restore, call on_result, return result dict."""
    with open(worker_file_path) as f:
        original_source = f.read()

    mutated = apply_mutant(clean_source, site)
    if os.environ.get("_MUTATE4PY_TEST_WORKER_WRITE_FAIL") == "1":
        raise WorkerFailureError(
            f"worker-{worker_idx} could not write file copy: injected test failure"
        )
    try:
        with open(worker_file_path, "w") as f:
            f.write(mutated)
    except OSError as e:
        raise WorkerFailureError(
            f"worker-{worker_idx} could not write file copy: {e}"
        ) from e

    try:
        status, _ = _run_command(test_command, worker_root, mutant_timeout)
    finally:
        try:
            with open(worker_file_path, "w") as f:
                f.write(original_source)
        except OSError as e:
            raise WorkerFailureError(
                f"worker-{worker_idx} could not restore file copy: {e}"
            ) from e

    result = {
        "worker_idx": worker_idx,
        "site": site,
        "site_idx": site_idx,
        "total": total,
        "status": status,
    }
    on_result(result)
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


def _assign_sites_to_workers(
    selected_sites: list[Site], n_workers: int
) -> dict[int, list[tuple[int, Site, int]]]:
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


def run_parallel(
    *,
    selected_sites: list[Site],
    clean_source: str,
    source_path: str,
    cwd: str,
    test_command: str,
    mutant_timeout: float,
    max_workers: int,
    on_result: Callable,
) -> tuple[dict, list[Site]]:
    """Run sites in parallel across max_workers isolated worker copies.

    on_result(result_dict) is called from worker threads as each site finishes —
    callers use this to print progress lines in arrival order.

    Returns (counts, survivors) sorted by stable site index.
    Raises WorkerFailureError on write/restore failure.
    Raises ParallelRunError if collected results != selected site count.
    """
    real_source = os.path.realpath(source_path)
    real_cwd = os.path.realpath(cwd)
    if not real_source.startswith(real_cwd + os.sep):
        raise ParallelRunError(
            f"target file must be inside working directory: {source_path}"
        )

    n_workers = min(max_workers, len(selected_sites))
    source_rel = os.path.relpath(real_source, real_cwd)

    pid = os.getpid()
    nanos = time.monotonic_ns()
    run_root = os.path.join(real_cwd, ".mutate4py", "workers", f"run-{pid}-{nanos}")

    try:
        worker_roots = _provision_workers(run_root, n_workers, real_cwd)
        by_worker = _assign_sites_to_workers(selected_sites, n_workers)

        short_fail = os.environ.get("_MUTATE4PY_TEST_WORKER_SHORT_RESULT") == "1"

        def _run_one_assignment(assignment: tuple[int, Site, int]) -> dict:
            worker_idx, site, site_idx = assignment
            return _run_one_site(
                worker_idx=worker_idx,
                site=site,
                site_idx=site_idx,
                total=len(selected_sites),
                clean_source=clean_source,
                worker_root=worker_roots[worker_idx - 1],
                worker_file_path=os.path.join(worker_roots[worker_idx - 1], source_rel),
                test_command=test_command,
                mutant_timeout=mutant_timeout,
                on_result=on_result,
            )

        # Sites for the same worker must run sequentially (same file path).
        # Group by worker, then run groups in parallel across workers.
        def _run_worker_group(
            worker_assignments: list[tuple[int, Site, int]],
        ) -> list[dict]:
            worker_results = [_run_one_assignment(a) for a in worker_assignments]
            if short_fail and worker_results:
                worker_results.pop()
            return worker_results

        results: list[dict] = []
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            futures = {
                executor.submit(_run_worker_group, assignments): worker_idx
                for worker_idx, assignments in by_worker.items()
            }
            for future in as_completed(futures):
                results.extend(future.result())

        if len(results) != len(selected_sites):
            raise ParallelRunError(
                f"mutation workers stopped after {len(results)}/{len(selected_sites)} results"
            )

        results.sort(key=lambda r: r["site_idx"])
        return _summarize_results(results)

    finally:
        shutil.rmtree(run_root, ignore_errors=True)


# mutate4py-manifest-begin
# {"version":1,"tested_at":"2026-06-29T00:38:23Z","module_hash":"4a45d8cc7f4a554ec0e23a98a9d7eaa8a8243acc161202fd049eadaa1e16af18","functions":[{"id":"func/_copy_tree","name":"_copy_tree","line":39,"end_line":49,"hash":"c58bb609c2788486f71a5287477fd9e6aa6100b60b256fe79a523b2f289d7a92"},{"id":"func/_provision_worker","name":"_provision_worker","line":52,"end_line":65,"hash":"cfb0b406de1e5ce6f02c057269610a19087703563ea62bb84dc09930cf05fd5b"},{"id":"func/_run_one_site","name":"_run_one_site","line":68,"end_line":116,"hash":"157b36ca55d127ce387cfbe581dfa09dae9fd7cc6ce5bedebfbfb2de32594634"},{"id":"func/_provision_workers","name":"_provision_workers","line":119,"end_line":127,"hash":"09af39ee078b9e32cf2b76f652e56ac4b1331413c051ac2234cf2d58bbc825a4"},{"id":"func/_assign_sites_to_workers","name":"_assign_sites_to_workers","line":130,"end_line":138,"hash":"5dbcd1617f148dd205dbfbfc44aaca0826b48c33f9d2de5a9d84e338b152f251"},{"id":"func/_summarize_results","name":"_summarize_results","line":141,"end_line":150,"hash":"1b677b32d8a08f9ab26553d77cdc8a86ebaef971b0f827bfcc1cf81a3b10339c"},{"id":"func/run_parallel","name":"run_parallel","line":153,"end_line":236,"hash":"daf2e447b67ed4d54616aaa6e98362ad32ec32202216b918af821211dab1b8fa"}]}
# mutate4py-manifest-end
