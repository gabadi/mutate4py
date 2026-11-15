"""Parallel worker engine (--max-workers >= 2, sites >= 2).

Each Worker is an isolated tree copy of the working directory with its own
uv venv (ADR 0015), and owns exactly one primed Executor — forking when
eligible, subprocess otherwise — chosen by that Worker's own subprocess
(`_worker_server.py`) at startup and held for the Worker's whole run. A
Mutant is dispatched over `_worker_protocol`'s request/response pipe; the
cost this design exists to avoid is a fresh `pytest` process per Mutant.

Per-site test-context narrowing (`_test_dispatch.plan_mutant`) is planned by
the orchestrator, once per Site, before dispatch; each Worker runs the plan it
is handed. Narrowing composes with parallel Workers exactly as it does with the
serial loop — neither path may special-case the other.
"""

import dataclasses
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from mutate4py._discovery import Site, apply_mutant
from mutate4py._executor import Executor, MutantTiming, combine_descriptions
from mutate4py._plugin_neutralisation import disabled_plugin_args
from mutate4py._worker_results import (
    ParallelRunResult,
    WorkerGroupOutcome,
    _assign_sites_to_workers,
    _drop_one_result_if_injected,
    _summarize_confirmation,
    _summarize_results,
    _summarize_selection,
    _summarize_timing,
)
from mutate4py._test_dispatch import (
    ControlRuns,
    ControlTarget,
    MutantPlan,
    PlanInputs,
    ConfirmationResult,
    SurvivorConfirmation,
    TimeoutPolicy,
    confirm_survivors,
    plan_sites,
)
from mutate4py._worker_lifecycle import (
    ParallelRunError,
    WorkerFailureError,
    _close_worker_executor,
    _describe_worker_executor,
    _prime_worker_executor,
)
from mutate4py._worker_protocol import ServerLaunch, WorkerProcessError, WorkerProcessExecutor
from mutate4py._worker_provision import (
    _copy_tree,
    _link_import_root,
    _provision_venv,
    _required_worker_distributions,
)

__all__ = ["ParallelRunError", "ParallelRunRequest", "ParallelRunResult", "WorkerFailureError", "run_parallel"]


@dataclasses.dataclass
class SiteAssignment:
    """One (site, worker) pairing, the MutantPlan built for that Site, and its
    position in the overall progress count."""

    worker_idx: int
    site: Site
    site_idx: int
    total: int
    worker_root: str
    worker_file_path: str
    plan: MutantPlan


@dataclasses.dataclass
class WorkerRunSettings:
    """Shared across every mutant run within one parallel dispatch. Holds no
    selection or timeout input: each SiteAssignment already carries its plan."""

    clean_source: str
    on_result: Callable
    abs_source_path: str = ""
    controls: ControlRuns = dataclasses.field(default_factory=ControlRuns)
    confirmation: SurvivorConfirmation | None = None


@dataclasses.dataclass
class ParallelRunRequest:
    selected_sites: list[Site]
    clean_source: str
    source_path: str
    cwd: str
    pytest_args: list[str]
    timeout_policy: TimeoutPolicy
    max_workers: int
    on_result: Callable
    selection_source: object = None
    abs_source_path: str = ""
    forking_requested: bool = True
    positionals: tuple[str, ...] = ()
    ran_at_import: frozenset[int] = frozenset()  # the guarded file's, for swap mode
    # Set to have each Worker re-run its own Survivors with the full set on its fresh interpreter, in its
    # own clone, before the clone is removed; None leaves every Survivor to the caller.
    confirmation: SurvivorConfirmation | None = None
    # Test-injection seam: when set, every Worker shares this one
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
    # plans[site_idx - 1] is the MutantPlan for that Site; site_idx counts from 1.
    plans: list[MutantPlan]
    settings: WorkerRunSettings
    n_workers: int


def _provision_worker(worker_root: str, required: frozenset[str]) -> None:
    """Provision one Worker copy; restate any uv or interpreter failure as a WorkerFailureError."""
    try:
        _provision_venv(worker_root, required)
    except subprocess.CalledProcessError as e:
        tail = "\n".join(e.stderr.splitlines()[-5:])
        raise WorkerFailureError(f"{' '.join(e.cmd)} failed in {worker_root}: {tail}") from e
    except OSError as e:
        raise WorkerFailureError(f"could not run uv in {worker_root}: {e}") from e
    except WorkerProcessError as e:
        raise WorkerFailureError(str(e)) from e


def _provision_worker_executors(
    worker_roots: list[str],
    source_rel: str,
    *,
    launch: ServerLaunch,
    injected_executor: Executor | None,
    source_root: str,
) -> list[Executor]:
    """One Executor per worker root: the shared injected fake when supplied
    (tests), a real per-Worker subprocess proxy otherwise.

    Each real proxy gets a distinct worker_id ("gw1", "gw2", ...) so
    pytest-django gives every Worker its own test database instead of
    colliding. Numbered from 1, matching `worker_roots`' own
    "worker-1", "worker-2", ... naming (`_provision_workers`) and the CLI
    progress line's `worker-{worker_idx}` — not pytest-xdist's 0-based "gw0"
    convention, which would leave the two identifiers for one Worker off by
    one and defeat the point of a human-readable suffix on disk."""
    if injected_executor is not None:
        return [injected_executor for _ in worker_roots]
    return [
        WorkerProcessExecutor(
            worker_root=root,
            guarded_path=os.path.join(root, source_rel),
            source_root=source_root,
            launch=dataclasses.replace(launch, worker_id=f"gw{i}"),
        )
        for i, root in enumerate(worker_roots, start=1)
    ]


def _run_one_site(assignment: SiteAssignment, executor: Executor, settings: WorkerRunSettings) -> dict:
    """Mutate the worker copy, dispatch this site's MutantPlan to executor.run(),
    restore, call on_result, return the result dict."""
    plan = assignment.plan
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
        started = time.monotonic()
        status = executor.run(plan.args, plan.timeout)
        seconds = time.monotonic() - started
        # Raises before a tally: a Mutant pytest never exercised must not count as `killed` (issue #55).
        target = ControlTarget(assignment.worker_file_path, settings.clean_source, executor, settings.abs_source_path)
        status = settings.controls.settle(status, plan, assignment.site, target)
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
        "selection": plan.selection,
        "seconds": seconds,
    }
    settings.on_result(result)
    return result


def _provision_workers(run_root: str, n_workers: int, real_cwd: str) -> list[str]:
    """Create and provision n_workers isolated tree copies; return their root paths."""
    worker_roots = []
    required = _required_worker_distributions(real_cwd)
    for k in range(1, n_workers + 1):
        worker_root = os.path.join(run_root, f"worker-{k}")
        _copy_tree(real_cwd, worker_root)
        _provision_worker(worker_root, required)
        # The mutate4py package dir: the Worker's only route to mutate4py (no orchestrator site-packages).
        try:
            _link_import_root(worker_root, os.path.dirname(os.path.abspath(__file__)))
        except (OSError, subprocess.CalledProcessError) as e:
            raise WorkerFailureError(f"could not link the mutate4py import root for {worker_root}: {e}") from e
        worker_roots.append(worker_root)
    return worker_roots


def _confirm_worker_survivors(
    worker_results: list[dict], executor: Executor, worker_file_path: str, settings: WorkerRunSettings
) -> tuple[ConfirmationResult, MutantTiming]:
    """Re-run this Worker's own Survivors with the full set on its fresh interpreter, in its own clone."""
    survivors = [r["site"] for r in worker_results if r["status"] == "survived"]
    if not survivors:
        return ConfirmationResult([], 0, 0), MutantTiming()
    target = ControlTarget(
        worker_file_path, settings.clean_source, executor.fresh_interpreter(), settings.abs_source_path
    )
    timing = MutantTiming()
    try:
        return confirm_survivors(survivors, target, settings.confirmation, timing), timing
    except WorkerProcessError as e:
        raise WorkerFailureError(f"confirmation in {worker_file_path} failed: {e}") from e


def _dispatch_worker_groups(plan: _WorkerDispatchPlan) -> list[WorkerGroupOutcome]:
    """Prime each Worker's executor once, describe it, run its whole assignment
    sequentially (same file path), confirm its Survivors when the plan asks, then
    close it — the executor is alive from priming to the end of that Worker's
    share of the run. Workers dispatch across plan.n_workers threads. Returns,
    ordered by Worker index, the outcome of each Worker that ran Mutants."""
    short_fail = os.environ.get("_MUTATE4PY_TEST_WORKER_SHORT_RESULT") == "1"

    def _run_worker_group(worker_idx: int, assignments: list[tuple[int, Site, int]]) -> WorkerGroupOutcome:
        executor = plan.executors[worker_idx - 1]
        worker_root = plan.worker_roots[worker_idx - 1]
        worker_file_path = os.path.join(worker_root, plan.source_rel)
        _prime_worker_executor(executor, worker_idx)
        try:
            description = _describe_worker_executor(executor, worker_idx)
            worker_results = [
                _run_one_site(
                    SiteAssignment(
                        worker_idx=worker_idx,
                        site=site,
                        site_idx=site_idx,
                        total=plan.total,
                        worker_root=worker_root,
                        worker_file_path=worker_file_path,
                        plan=plan.plans[site_idx - 1],
                    ),
                    executor,
                    plan.settings,
                )
                for (_, site, site_idx) in assignments
            ]
            outcome = WorkerGroupOutcome(
                _drop_one_result_if_injected(worker_results, short_fail=short_fail), description
            )
            if plan.settings.confirmation is not None:
                outcome.confirmation, outcome.confirmation_timing = _confirm_worker_survivors(
                    worker_results, executor, worker_file_path, plan.settings
                )
        finally:
            _close_worker_executor(executor)
        return outcome

    outcomes: dict[int, WorkerGroupOutcome] = {}
    with ThreadPoolExecutor(max_workers=plan.n_workers) as executor_pool:
        futures = {
            executor_pool.submit(_run_worker_group, worker_idx, assignments): worker_idx
            for worker_idx, assignments in plan.by_worker.items()
        }
        for future in as_completed(futures):
            outcomes[futures[future]] = future.result()
    return [outcomes[worker_idx] for worker_idx in sorted(outcomes)]


def _plan_inputs(request: ParallelRunRequest) -> PlanInputs:
    return PlanInputs(
        pytest_args=request.pytest_args,
        selection_source=request.selection_source,
        abs_source_path=request.abs_source_path,
        timeout_policy=request.timeout_policy,
        positionals=request.positionals,
        cwd=request.cwd,
    )


def _run_settings(request: ParallelRunRequest) -> WorkerRunSettings:
    return WorkerRunSettings(
        clean_source=request.clean_source,
        on_result=request.on_result,
        abs_source_path=request.abs_source_path,
        confirmation=request.confirmation,
    )


def run_parallel(request: ParallelRunRequest) -> ParallelRunResult:
    """Run sites in parallel across max_workers isolated Workers, each owning
    exactly one primed Executor for the whole run.

    on_result(result_dict) is called from worker threads as each site finishes —
    callers use this to print progress lines in arrival order.

    Returns a ParallelRunResult: counts and survivors sorted by stable site index,
    selection_counts (None unless a selection source is in play), the Mutants'
    timing, and the combined description of the Workers that ran Mutants.
    Raises WorkerFailureError on write/restore/dispatch failure.
    Raises ParallelRunError if collected results != selected site count.
    A NoTestsCollectedError (case 4) propagates uncaught.
    """
    real_source = os.path.realpath(request.source_path)
    real_cwd = os.path.realpath(request.cwd)
    if not real_source.startswith(real_cwd + os.sep):
        raise ParallelRunError(f"target file must be inside working directory: {request.source_path}")

    selected_sites = request.selected_sites
    n_workers = min(request.max_workers, len(selected_sites))
    source_rel = os.path.relpath(real_source, real_cwd)
    run_root = os.path.join(real_cwd, ".mutate4py", "workers", f"run-{os.getpid()}-{time.monotonic_ns()}")

    try:
        # Planned before any Worker is provisioned, so a selection disagreement
        # aborts the run before a single Mutant is dispatched.
        plans = plan_sites(selected_sites, _plan_inputs(request))
        worker_roots = _provision_workers(run_root, n_workers, real_cwd)
        by_worker = _assign_sites_to_workers(selected_sites, n_workers)
        executors = _provision_worker_executors(
            worker_roots,
            source_rel,
            launch=ServerLaunch(
                forking_requested=request.forking_requested,
                prime_args=tuple(disabled_plugin_args(request.pytest_args)),
                ran_at_import=request.ran_at_import,
            ),
            injected_executor=request.executor,
            source_root=real_cwd,
        )
        groups = _dispatch_worker_groups(
            _WorkerDispatchPlan(
                by_worker=by_worker,
                worker_roots=worker_roots,
                executors=executors,
                source_rel=source_rel,
                total=len(selected_sites),
                plans=plans,
                settings=_run_settings(request),
                n_workers=n_workers,
            )
        )

        results = [r for group in groups for r in group.results]
        if len(results) != len(selected_sites):
            raise ParallelRunError(f"mutation workers stopped after {len(results)}/{len(selected_sites)} results")

        results.sort(key=lambda r: r["site_idx"])
        counts, survivors = _summarize_results(results)
        selection_counts = _summarize_selection(results) if request.selection_source is not None else None
        return ParallelRunResult(
            counts=counts,
            survivors=survivors,
            selection_counts=selection_counts,
            timing=_summarize_timing(results, [g.confirmation_timing for g in groups]),
            executor_description=combine_descriptions([g.description for g in groups]),
            confirmation=_summarize_confirmation(groups),
        )

    finally:
        shutil.rmtree(run_root, ignore_errors=True)
