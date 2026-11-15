"""The report of a run that skips its Measurement (design 89 §5b).

A skipped run runs no Mutant and writes nothing. It prints the skipped Measurement line, the
Survivors its stored Manifests record (each labelled with its file, since a batch shares one block),
and the Time line, which reads zero because no Mutant ran. Its exit code is the one a scored run gives
for those Survivors. It prints no Mutation Report: nothing was scored in this run.
"""

import os
from collections.abc import Sequence

from mutate4py._exit_codes import scored_run_exit_code
from mutate4py._executor import MutantTiming
from mutate4py._manifest import recorded_survivors
from mutate4py._report import _recorded_block_lines
from mutate4py._scoring import ScoredRun

SKIPPED_MEASUREMENT_LINE = "Measurement: skipped (code and tests unchanged since the last scored run)"


def recorded_survivors_kept(written: dict, scored_run: ScoredRun) -> list[tuple[str, dict]]:
    """The survivors the written Manifest keeps on functions this run did not re-score (#106).

    A skipped function is not re-run, so its recorded survivors stay as they were; they are
    reported apart from this run's Survivors and count toward the exit code.
    """
    rescored = scored_run.function_scores([fn["id"] for fn in written["functions"]])
    return [(fid, s) for fid, s in recorded_survivors(written) if fid not in rescored]


def skipped_run_report(
    targets: Sequence[tuple[str, dict]],
    *,
    cwd: str,
    allow_survivors: bool,
) -> tuple[list[str], int]:
    """The lines a skipped run prints for its (path, stored Manifest) targets, and its exit code."""
    recorded = [
        (f"{os.path.relpath(path, cwd)} {fid}", survivor)
        for path, manifest in targets
        for fid, survivor in recorded_survivors(manifest)
    ]
    lines = [
        "",
        SKIPPED_MEASUREMENT_LINE,
        *_recorded_block_lines(recorded),
        "",
        MutantTiming().render(),
    ]
    return lines, scored_run_exit_code(len(recorded), allow_survivors=allow_survivors)
