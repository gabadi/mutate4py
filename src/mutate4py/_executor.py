"""The executor interface both mutant-execution paths implement: prime once
for a given `cwd`, then run a given pytest argument list under a timeout and
report how the mutant classified.

`ForkingExecutor` (`_forking_executor.py`) and `SubprocessExecutor`
(`_subprocess_executor.py`) both satisfy this structurally — no inheritance
required, so the run loop that only ever holds `Executor` never needs to
know which one it has.
"""

import dataclasses
from typing import Protocol

__all__ = ["Executor", "ExecutorDescription", "MutantTiming", "combine_descriptions"]


@dataclasses.dataclass(frozen=True)
class ExecutorDescription:
    """A read-only account of how an Executor ran its Mutants, for the report's Executor line."""

    mode: str
    reason: str = ""
    fresh_import: int = 0

    def render(self) -> str:
        if self.mode == "forking":
            return f"forking (fresh import {self.fresh_import})"
        return f"{self.mode} ({self.reason})"


def combine_descriptions(descriptions: list[ExecutorDescription]) -> ExecutorDescription:
    """One Executor line for a parallel run, from the description each Worker gave of its own executor.

    All forking: forking, with the Workers' fresh imports summed. None forking:
    subprocess, with the distinct reasons they gave. A mix: mixed, naming how many
    Workers forked and why the rest did not.
    """
    if not descriptions:
        raise ValueError("no Workers to describe")
    forked = [d for d in descriptions if d.mode == "forking"]
    plain = [d for d in descriptions if d.mode != "forking"]
    if not plain:
        return ExecutorDescription(mode="forking", fresh_import=sum(d.fresh_import for d in forked))
    reasons = "; ".join(dict.fromkeys(d.reason for d in plain))
    if not forked:
        return ExecutorDescription(mode="subprocess", reason=reasons)
    total = len(descriptions)
    fresh = sum(d.fresh_import for d in forked)
    return ExecutorDescription(
        mode="mixed",
        reason=(
            f"forking on {len(forked)} of {total} workers, fresh import {fresh}; "
            f"subprocess on {len(plain)} of {total} workers: {reasons}"
        ),
    )


@dataclasses.dataclass
class MutantTiming:
    """Wall time a run spent on its Mutants and on survivor confirmation, for the report's Time line.

    A timed-out Mutant lands in the timeouts bucket rather than the mutants one,
    so a run dominated by hangs shows as such. A confirmation timeout folds into
    killed, the same way the Mutation Report counts it (ADR 0011).
    """

    mutants_seconds: float = 0.0
    mutants_count: int = 0
    timeouts_seconds: float = 0.0
    timeouts_count: int = 0
    confirmation_seconds: float = 0.0
    confirmation_runs: int = 0
    confirmation_kills: int = 0

    def record(self, status: str, seconds: float) -> None:
        if status == "timeout":
            self.timeouts_seconds += seconds
            self.timeouts_count += 1
        else:
            self.mutants_seconds += seconds
            self.mutants_count += 1

    def record_confirmation(self, status: str, seconds: float) -> None:
        self.confirmation_seconds += seconds
        self.confirmation_runs += 1
        if status in ("killed", "timeout"):
            self.confirmation_kills += 1

    def merge(self, other: "MutantTiming") -> None:
        """Add another run's timing into this one, for the batch's running total."""
        self.mutants_seconds += other.mutants_seconds
        self.mutants_count += other.mutants_count
        self.timeouts_seconds += other.timeouts_seconds
        self.timeouts_count += other.timeouts_count
        self.confirmation_seconds += other.confirmation_seconds
        self.confirmation_runs += other.confirmation_runs
        self.confirmation_kills += other.confirmation_kills

    def render(self) -> str:
        return (
            f"Time: mutants {self.mutants_seconds:.2f}s ({self.mutants_count}), "
            f"timeouts {self.timeouts_seconds:.2f}s ({self.timeouts_count}), "
            f"confirmation {self.confirmation_seconds:.2f}s "
            f"({self.confirmation_runs} run, {self.confirmation_kills} killed)"
        )


class Executor(Protocol):
    def prime(self) -> None: ...

    def run(self, args: list[str], timeout: float) -> str: ...

    def describe(self) -> ExecutorDescription: ...
