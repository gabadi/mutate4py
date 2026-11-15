"""Per-Mutant dispatch planning: builds the MutantPlan (pytest argument list,
timeout, selection tally) for one Site given its Selection outcome, and settles a
Mutant whose pytest ran no test with a Control run on the original code.

The plan is computed by the orchestrator before dispatch and shared by both
execution paths — the serial loop (`_execution.py`) and parallel Workers
(`_workers.py`) — which is why it sits in the domain layer rather than in
either caller. Planning reads the filesystem to check that node id files exist
(see `plan_mutant`); a Control run writes the original source to the guarded
file and dispatches to an Executor (see `ControlRuns`). See tach.toml before
moving it.
"""

import dataclasses
import logging
import os
from collections.abc import Callable

from mutate4py._discovery import Site
from mutate4py._executor import Executor
from mutate4py._pytest_argv import POSITIONAL, token_roles

__all__ = [
    "NO_TESTS_HINT",
    "ControlRuns",
    "ControlTarget",
    "MutantPlan",
    "NoTestsCollectedError",
    "PlanInputs",
    "TimeoutPolicy",
    "_log_dispatch_abort",
    "confirm_plan",
    "plan_mutant",
    "plan_sites",
]

_logger = logging.getLogger(__name__)


class NoTestsCollectedError(Exception):
    """A selected site whose test run exercised no test at all (case 4)."""


# pytest exits 4 (usage error) or 5 (no tests collected) when it runs no test for a
# Mutant. Either the argv it was given is the defect, or the Mutant broke the run (a
# module that raises at import fails the conftest import). `ControlRuns` tells the
# two apart; only a defect of the argv aborts the run.
_ABORT_HINTS = {
    "no-tests-collected": "pytest collected no tests to run (exit 5): a --pytest-args filter "
    "or a node-ID path mismatch deselected everything",
    "usage-error": "pytest exited with a usage error before collecting any test (exit 4): check --pytest-args",
}
NO_TESTS_HINT = _ABORT_HINTS["no-tests-collected"]
"""The hint a run whose pytest collected nothing carries, shared by every path that reports it."""

_NO_TEST_RAN = frozenset(_ABORT_HINTS)
"""The Executor statuses of a pytest that ran no test: exit 4 (usage-error) and exit 5 (no-tests-collected)."""

_TESTS_RAN = frozenset({"survived", "killed"})
"""The Executor statuses that show pytest ran tests: exit 0 (all passed) and exit 1 (a test failed)."""

# How a Control run ended, for the abort message: it ran on the original code and showed no test ran.
_CONTROL_ENDED = {
    "usage-error": "exited with a usage error (exit 4)",
    "no-tests-collected": "collected no tests (exit 5)",
    "timeout": "timed out after {timeout:g}s",
    "errored": "ended with no test result (pytest was interrupted, crashed or did not start)",
}


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
    policy, the selection source that answers for abs_source_path, and the directory
    pytest runs in (cwd), which the node ids of a narrowed Mutant must resolve from.
    """

    pytest_args: list[str]
    selection_source: object
    abs_source_path: str
    timeout_policy: TimeoutPolicy
    positionals: tuple[str, ...]
    cwd: str


@dataclasses.dataclass(frozen=True)
class ControlTarget:
    """Where a Control run happens: the file a Mutant is spliced into, the original source to put back
    there, the Executor that runs it, and the guarded file's absolute path, which an abort names."""

    path: str
    clean_source: str
    executor: Executor
    abs_source_path: str


def _control_run(target: ControlTarget, plan: MutantPlan) -> str:
    """Run `plan` against the original code: restore `clean_source` at `target.path`, then dispatch.

    The caller's own restore, or its next splice, still follows; this leaves the original at `path`.
    The Executor is told it is a Control run, so it leaves the run out of its Mutant counts.
    """
    with open(target.path, "w") as f:
        f.write(target.clean_source)
    return target.executor.run(plan.args, plan.timeout, control=True)


def _control_abort(where: str, status: str, control: str, plan: MutantPlan) -> NoTestsCollectedError:
    """The abort for a Mutant that ended in `status` whose Control run ended in `control` (neither ran tests).

    A Control run that ends in exit 4 or 5 too says the args are the defect. One that timed out or errored
    says nothing of the args, and the abort says so: the Mutant's own exit alone would tell the user to
    check --pytest-args for an argv that may be fine.
    """
    gave = _CONTROL_ENDED.get(control, f"ended in {control}").format(timeout=plan.timeout)
    message = f"{where}: {_ABORT_HINTS[status]}. A Control run of the same pytest args on the original code {gave}"
    if control in _NO_TEST_RAN:
        return NoTestsCollectedError(f"{message} too")
    return NoTestsCollectedError(f"{message}, so it did not show whether the args or the Mutant caused the exit")


@dataclasses.dataclass
class ControlRuns:
    """The argvs whose Control run showed that pytest runs tests on the original code.

    A Mutant whose pytest exits 4 or 5 ran no test, for one of two causes: the argv is
    the defect, or the Mutant broke the run. Exit codes cannot tell them apart, so the
    first such Mutant of an argv gets a Control run: the same argv on the original code.
    Only exit 0 or 1 there (`survived`, `killed`) shows that tests ran: then the Mutant
    caused the exit, and every later 4 or 5 of that argv needs no further Control run.
    Any other end (4 or 5 again, a timeout, `errored`) shows nothing, so the argv stays
    the suspect and the run aborts.
    """

    cleared: set[tuple[str, ...]] = dataclasses.field(default_factory=set)

    def settle(self, status: str, plan: MutantPlan, site: Site, target: ControlTarget) -> str:
        """The Classification (killed, survived or timeout) to tally for the Mutant of `site` that ended in `status`.

        `errored` (pytest ended without a result: exit 2 or 3, a signal, a start that failed) is a
        kill, as for any Mutant. Exit 4 and 5 are settled: "killed" when the argv is cleared or a
        Control run (the same argv on the original code, through `target`) ran tests. Any other
        status returns unchanged and makes no Control run.

        Raises NoTestsCollectedError if exit 4 or 5 is not cleared and the Control run ran no test.
        """
        if status == "errored":
            return "killed"
        if status not in _NO_TEST_RAN:
            return status
        key = tuple(plan.args)
        if key not in self.cleared:
            control = _control_run(target, plan)
            if control not in _TESTS_RAN:
                raise _control_abort(f"{target.abs_source_path}:{site.line}", status, control, plan)
            self.cleared.add(key)
        return "killed"


def _check_node_ids_resolve(node_ids: list[str], cwd: str, where: str) -> None:
    """Raise NoTestsCollectedError if a node id names a file that does not exist under cwd."""
    for node_id in node_ids:
        if not os.path.exists(os.path.join(cwd, node_id.split("::", 1)[0])):
            raise NoTestsCollectedError(
                f"{where}: pytest would exit 4 on node id {node_id}: its file is not under {cwd}. "
                "Node ids are relative to the pytest rootdir: run mutate4py from there"
            )


def plan_mutant(site: Site, inputs: PlanInputs) -> MutantPlan:
    """Return the MutantPlan for site; selection is None without a selection source.

    The selection source is the Measurement, which answers
    `tests_for_line(path, line)`. "narrowed" runs only the tests covering
    site.line, with the run's positional path args (`positionals`) removed from
    pytest_args so the path does not run beside the node ids; "static" runs the
    full pytest_args because the line executes at import time and no test owns
    it. "uncovered" (a line no test reached) also runs the full pytest_args,
    tallied as "static".

    The Measurement records node ids relative to its pytest rootdir, and pytest resolves
    them from the directory it runs in. A node id whose file does not exist under
    `inputs.cwd` is a pytest exit 4 for every Mutant, so it raises NoTestsCollectedError here,
    before any Mutant runs: left to the Mutants, that exit races the Mutant timeout.
    """
    if inputs.selection_source is None:
        return MutantPlan(list(inputs.pytest_args), inputs.timeout_policy.timeout_for(None), None)
    outcome, node_ids = inputs.selection_source.tests_for_line(inputs.abs_source_path, site.line)
    if outcome == "narrowed":
        _check_node_ids_resolve(node_ids, inputs.cwd, f"{inputs.abs_source_path}:{site.line}")
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
