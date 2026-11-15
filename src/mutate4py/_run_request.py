"""The request a mutation run is made from, kept apart from the run loop that reads it."""

import dataclasses

from mutate4py._executor import Executor, MutantTiming
from mutate4py._measurement import Measurement

__all__ = ["RunMutationsRequest"]


@dataclasses.dataclass
class RunMutationsRequest:
    """Everything a mutation run needs: target, test invocation,
    selection/execution knobs, and manifest storage.
    """

    path: str
    source: str
    pytest_args: list[str]
    timeout_factor: int
    warning_threshold: int
    cwd: str
    max_workers: int = 0
    min_timeout: float = 5.0
    manifest_file: bool = False
    forking_requested: bool = True
    executor: Executor | None = None
    allow_survivors: bool = False
    # The run's Measurement when the caller took it (a batch run takes one for all its
    # files); None makes the run measure itself and print the Measurement lines.
    measurement: Measurement | None = None
    # A batch's running Time total: this run's timing is added to it once the run reports.
    timing_sink: MutantTiming | None = None
