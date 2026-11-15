"""Pure tallies over a parallel dispatch's per-Mutant result dicts, kept apart from
`_workers.py`'s provisioning and dispatch so each stays small enough to read whole.
"""

import dataclasses
from collections import defaultdict
from collections.abc import Sequence

from mutate4py._discovery import Site
from mutate4py._executor import ExecutorDescription, MutantTiming, combine_descriptions
from mutate4py._test_dispatch import ConfirmationResult

__all__ = [
    "ParallelRunResult",
    "WorkerGroupOutcome",
    "_assign_sites_to_workers",
    "_build_result",
    "_drop_one_result_if_injected",
    "_summarize_results",
    "_summarize_confirmation",
    "_summarize_selection",
    "_summarize_timing",
]


@dataclasses.dataclass
class ParallelRunResult:
    """What one parallel dispatch hands back: the tallies, the Survivors in site
    order, the selection tally (None without a selection source), the Mutants'
    timing, and the Executor description the Workers gave of themselves. `confirmation`
    is what the Workers' own confirmation of their Survivors gave, None when they made none
    and the caller confirms `survivors` itself."""

    counts: dict[str, int]
    survivors: list[Site]
    selection_counts: dict[str, int] | None
    timing: MutantTiming
    executor_description: ExecutorDescription
    confirmation: ConfirmationResult | None = None


@dataclasses.dataclass
class WorkerGroupOutcome:
    results: list[dict]
    description: ExecutorDescription
    confirmation: ConfirmationResult | None = None
    confirmation_timing: MutantTiming = dataclasses.field(default_factory=MutantTiming)


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


def _summarize_timing(results: list[dict], confirmations: Sequence[MutantTiming] = ()) -> MutantTiming:
    """Add each Mutant's own elapsed run time to the bucket its status names, and each Worker's confirmation time."""
    timing = MutantTiming()
    for r in results:
        timing.record(r["status"], r["seconds"])
    for confirmation_timing in confirmations:
        timing.merge(confirmation_timing)
    return timing


def _summarize_confirmation(groups: list[WorkerGroupOutcome]) -> ConfirmationResult | None:
    confirmed = [g.confirmation for g in groups if g.confirmation is not None]
    return _merge_confirmations(confirmed) if confirmed else None


def _merge_confirmations(confirmed: list[ConfirmationResult]) -> ConfirmationResult:
    still = sorted((site for c in confirmed for site in c.still), key=lambda s: s.index)
    return ConfirmationResult(still, sum(c.runs for c in confirmed), sum(c.kills for c in confirmed))


def _summarize_selection(results: list[dict]) -> dict[str, int]:
    """Tally narrowed/static selection counts, mirroring the serial loop's tally."""
    counts = {"narrowed": 0, "static": 0}
    for r in results:
        selection = r.get("selection")
        if selection is not None:
            counts[selection] += 1
    return counts


def _build_result(groups: list[WorkerGroupOutcome], results: list[dict], *, with_selection: bool) -> ParallelRunResult:
    counts, survivors = _summarize_results(results)
    return ParallelRunResult(
        counts=counts,
        survivors=survivors,
        selection_counts=_summarize_selection(results) if with_selection else None,
        timing=_summarize_timing(results, [g.confirmation_timing for g in groups]),
        executor_description=combine_descriptions([g.description for g in groups]),
        confirmation=_summarize_confirmation(groups),
    )


def _drop_one_result_if_injected(worker_results: list[dict], *, short_fail: bool) -> list[dict]:
    """Test-injection seam (_MUTATE4PY_TEST_WORKER_SHORT_RESULT=1): silently
    lose one Worker's last result, so run_parallel's own
    results-vs-sites reconciliation can be proven to fire."""
    if short_fail and worker_results:
        return worker_results[:-1]
    return worker_results
