"""The executor interface both mutant-execution paths implement: prime once
for a given `cwd`, then run a given pytest argument list under a timeout and
report how the mutant classified.

`ForkingExecutor` (`_forking_executor.py`) and `SubprocessExecutor`
(`_subprocess_executor.py`) both satisfy this structurally — no inheritance
required, so the run loop that only ever holds `Executor` never needs to
know which one it has.
"""

import dataclasses
import enum
from typing import Protocol

__all__ = ["Executor", "ExecutorDescription", "FileMode", "MutantTiming", "combine_descriptions"]


class FileMode(enum.StrEnum):
    HARNESS = "harness"
    SWAP = "swap"
    FRESH_IMPORT = "fresh import"
    FRESH_INTERPRETER = "fresh interpreter"


@dataclasses.dataclass(frozen=True)
class ExecutorDescription:
    """A read-only account of how an Executor ran its Mutants, for the report's Executor line."""

    mode: str
    reason: str = ""
    fresh_import: int = 0
    swap: int = 0
    fresh_interpreter: int = 0
    file_mode: str = ""

    def mode_counts(self) -> str:
        """How many Mutants ran by each forking mode, as the Executor line spells it."""
        return f"fresh import {self.fresh_import}, swap {self.swap}, fresh interpreter {self.fresh_interpreter}"

    def render(self) -> str:
        if self.mode == "forking":
            return f"forking ({self.mode_counts()})"
        return f"{self.mode} ({self.reason})"


def _split_by_mode(
    descriptions: list[ExecutorDescription],
) -> tuple[list[ExecutorDescription], list[ExecutorDescription]]:
    forked = [d for d in descriptions if d.mode == "forking"]
    return forked, [d for d in descriptions if d.mode != "forking"]


def _reasons(plain: list[ExecutorDescription]) -> str:
    return "; ".join(dict.fromkeys(d.reason for d in plain))


def _summed_forking(forked: list[ExecutorDescription]) -> ExecutorDescription:
    return ExecutorDescription(
        mode="forking",
        fresh_import=sum(d.fresh_import for d in forked),
        swap=sum(d.swap for d in forked),
        fresh_interpreter=sum(d.fresh_interpreter for d in forked),
    )


def _mixed_description(forked: list[ExecutorDescription], plain: list[ExecutorDescription]) -> ExecutorDescription:
    total = len(forked) + len(plain)
    return ExecutorDescription(
        mode="mixed",
        reason=(
            f"forking on {len(forked)} of {total} workers, {_summed_forking(forked).mode_counts()}; "
            f"subprocess on {len(plain)} of {total} workers: {_reasons(plain)}"
        ),
    )


def combine_descriptions(descriptions: list[ExecutorDescription]) -> ExecutorDescription:
    """One Executor line for a parallel run, from the description each Worker gave of its own executor.

    All forking: forking, with each of the Workers' mode counts summed. None forking:
    subprocess, with the distinct reasons they gave. A mix: mixed, naming how many
    Workers forked and why the rest did not.
    """
    if not descriptions:
        raise ValueError("no Workers to describe")
    forked, plain = _split_by_mode(descriptions)
    if not plain:
        return _summed_forking(forked)
    if forked:
        return _mixed_description(forked, plain)
    return ExecutorDescription(mode="subprocess", reason=_reasons(plain))


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
            f"({self.confirmation_runs} run, {self.confirmation_kills} kills)"
        )


class Executor(Protocol):
    def prime(self) -> None: ...

    def run(
        self,
        args: list[str],
        timeout: float,
        *,
        control: bool = False,  # mutate4py: equivalent a Protocol method has no body that reads the flag
    ) -> str:
        """Run pytest once over args and classify how it ended.

        `control` marks a Control run: a re-run of the same args on the original code, which proves nothing
        about a Mutant. An Executor that counts its Mutants leaves a Control run out of the count.
        """
        ...

    def describe(self) -> ExecutorDescription: ...

    def fresh_interpreter(self) -> "Executor": ...
