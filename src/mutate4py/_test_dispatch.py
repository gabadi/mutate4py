"""Per-Mutant dispatch planning: builds the MutantPlan (pytest argument list,
timeout, selection tally) for one Site given its Selection outcome.

The plan is computed by the orchestrator before dispatch and shared by both
execution paths — the serial loop (`_execution.py`) and parallel Workers
(`_workers.py`) — which is why it sits in the domain layer rather than in
either caller. See tach.toml before moving it.
"""

import dataclasses
import logging
from collections.abc import Callable

from mutate4py._discovery import Site
from mutate4py._pytest_argv import POSITIONAL, token_roles

__all__ = [
    "NO_TESTS_HINT",
    "MutantPlan",
    "NoTestsCollectedError",
    "PlanInputs",
    "TimeoutPolicy",
    "_check_execution_status",
    "_log_dispatch_abort",
    "confirm_plan",
    "plan_mutant",
    "plan_sites",
]

_logger = logging.getLogger(__name__)


class NoTestsCollectedError(Exception):
    """A selected site whose test run exercised no test at all (case 4)."""


# pytest exits 4 (usage error) or 5 (no tests collected) when it runs no test
# for a Mutant: the argv it was given, not the code under test, is the defect.
_ABORT_HINTS = {
    "no-tests-collected": "pytest collected no tests to run (exit 5): a --pytest-args filter "
    "or a node-ID path mismatch deselected everything",
    "usage-error": "pytest exited with a usage error before collecting any test (exit 4): check --pytest-args",
}
NO_TESTS_HINT = _ABORT_HINTS["no-tests-collected"]
"""The hint a run whose pytest collected nothing carries, shared by every path that reports it."""


def _check_execution_status(status: str, abs_source_path: str, site: Site) -> None:
    """Raise NoTestsCollectedError if status means pytest ran no test at all for site."""
    hint = _ABORT_HINTS.get(status)
    if hint is not None:
        raise NoTestsCollectedError(f"{abs_source_path}:{site.line}: {hint}")


def _log_dispatch_abort(exc: NoTestsCollectedError) -> int:
    """Log a case-4 abort (pytest ran no test for a Mutant); it exits 2."""
    _logger.error(f"error: pytest ran no test for a Mutant: {exc}")
    return 2


def _without_positionals(pytest_args: list[str], positionals: tuple[str, ...]) -> list[str]:
    """pytest_args minus the run's positional path arguments, which a narrowed Mutant replaces with node ids.

    A token is a positional only when the shared argv reader (`_pytest_argv`) reads
    it so, not the value of a value-taking option, so `-k tests` keeps its `tests`.
    Each positional is dropped once.
    """
    remaining = list(positionals)
    kept: list[str] = []
    for token, role in zip(pytest_args, token_roles(pytest_args)):
        if role == POSITIONAL and token in remaining:
            remaining.remove(token)
        else:
            kept.append(token)
    return kept


@dataclasses.dataclass(frozen=True)
class TimeoutPolicy:
    """How a Mutant's timeout is derived: max(min_timeout, factor x budget) + overhead.

    budget_of maps the node ids a Mutant runs to their budget (the summed measured
    durations of those tests plus the largest fixture setup in their files);
    budget_of(None) is the full test set's budget, which a static Mutant runs.
    overhead is the Per-Mutant overhead, the wall time spent outside the tests.
    """

    factor: float
    min_timeout: float
    overhead: float
    budget_of: Callable[[frozenset[str] | None], float]

    def timeout_for(self, node_ids: frozenset[str] | None) -> float:
        return max(self.min_timeout, self.factor * self.budget_of(node_ids)) + self.overhead


@dataclasses.dataclass(frozen=True)
class MutantPlan:
    """What one Mutant dispatches: the pytest argv, its timeout, and its selection tally."""

    args: list[str]
    timeout: float
    selection: str | None


@dataclasses.dataclass(frozen=True)
class PlanInputs:
    """The per-run inputs every Mutant's plan is built from: the run's pytest args,
    its positional path args (stripped from a narrowed Mutant's argv), its timeout
    policy, and the selection source that answers for abs_source_path.
    """

    pytest_args: list[str]
    selection_source: object
    abs_source_path: str
    timeout_policy: TimeoutPolicy
    positionals: tuple[str, ...]


def plan_mutant(site: Site, inputs: PlanInputs) -> MutantPlan:
    """Return the MutantPlan for site; selection is None without a selection source.

    The selection source is the Measurement, which answers
    `tests_for_line(path, line)`. "narrowed" runs only the tests covering
    site.line, with the run's positional path args (`positionals`) removed from
    pytest_args so the path does not run beside the node ids; "static" runs the
    full pytest_args because the line executes at import time and no test owns
    it. "uncovered" (a line no test reached) also runs the full pytest_args,
    tallied as "static".
    """
    if inputs.selection_source is None:
        return MutantPlan(list(inputs.pytest_args), inputs.timeout_policy.timeout_for(None), None)
    outcome, node_ids = inputs.selection_source.tests_for_line(inputs.abs_source_path, site.line)
    if outcome == "narrowed":
        return MutantPlan(
            [*_without_positionals(inputs.pytest_args, inputs.positionals), *node_ids],
            inputs.timeout_policy.timeout_for(frozenset(node_ids)),
            "narrowed",
        )
    if outcome in ("static", "uncovered"):
        return MutantPlan(list(inputs.pytest_args), inputs.timeout_policy.timeout_for(None), "static")
    # Every other outcome raises, so an unrecognized one can never fall through to
    # a full-suite run that the report would then miscount as narrowed.
    raise ValueError(f"{inputs.abs_source_path}:{site.line}: unrecognized selection outcome {outcome!r}")


def confirm_plan(pytest_args: list[str], timeout_policy: TimeoutPolicy) -> MutantPlan:
    """Return the MutantPlan that confirms a Survivor: the full test set, unnarrowed.

    A Survivor of a narrowed Mutant may survive only because its covering tests
    did not reach the state a later test reads, so it is re-run with every test
    the run selects: pytest_args verbatim (positional path kept), budgeted as the
    full set. Confirmation is never narrowed, so its selection tally is None.
    """
    return MutantPlan(list(pytest_args), timeout_policy.timeout_for(None), None)


def plan_sites(sites: list[Site], inputs: PlanInputs) -> list[MutantPlan]:
    """Return the MutantPlan of each site, in the order given."""
    return [plan_mutant(site, inputs) for site in sites]
