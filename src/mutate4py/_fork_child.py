"""What a forked child of the forking executor decides before pytest starts,
kept out of the fork plumbing so it can be tested in-process.

`child_mode` turns the guarded file's mode (decided at prime) into how this
one Mutant runs: "fresh import", "swap" or "fresh interpreter". In swap mode
the fork server primed a guarded file that prime itself imported (a conftest
or a plugin did), so every forked child holds the clean module: `swap_in`
plans the body swap from the clean source (`swap_side`, read at prime) to the
mutated file on disk (`_code_swap.plan_swap`) and applies it to the live
functions prime built. Any refusal means a fresh interpreter instead. The
child reports its mode through a pipe; `read_report` and `reported_mode`
turn that back into the mode `describe` counts.
"""

import dataclasses
import gc
import os
from collections.abc import Sequence
from types import FunctionType

from mutate4py._code_swap import Refusal, plan_swap
from mutate4py._executor import FileMode

__all__ = [
    "SwapSource",
    "child_mode",
    "live_functions_of",
    "read_report",
    "report_mode",
    "reported_mode",
    "swap_in",
    "swap_side",
]

_REPORTED_MODES = (FileMode.FRESH_IMPORT, FileMode.SWAP, FileMode.FRESH_INTERPRETER)


@dataclasses.dataclass(frozen=True)
class SwapSource:
    """The clean side of every swap: the guarded file's source as prime saw it, the
    filename its live code was compiled under, and the lines the Measurement saw
    run under the Empty context (a changed body among them ran at import)."""

    clean_source: str
    filename: str
    ran_at_import: frozenset[int]


def swap_side(file_mode: str, guarded_path: str, ran_at_import: frozenset[int]) -> tuple[SwapSource, list]:
    """What every swap child plans from, read at prime: the clean source and the live
    functions built from it. Nothing for a file not in swap mode."""
    if file_mode != FileMode.SWAP:
        return SwapSource("", guarded_path, ran_at_import), []
    with open(guarded_path) as f:
        clean_source = f.read()
    live = live_functions_of(guarded_path)
    filename = live[0].__code__.co_filename if live else guarded_path
    return SwapSource(clean_source, filename, ran_at_import), live


def child_mode(file_mode: str, source: SwapSource, guarded_path: str, live: Sequence[FunctionType]) -> FileMode:
    """How this child runs its Mutant, from the guarded file's mode: a fresh import
    in-process, a swap (refused into a fresh interpreter by `swap_in`), or, for a
    harness file, a fresh interpreter."""
    if file_mode == FileMode.SWAP:
        return swap_in(source, guarded_path, live)
    return FileMode.FRESH_IMPORT if file_mode == FileMode.FRESH_IMPORT else FileMode.FRESH_INTERPRETER


def swap_in(source: SwapSource, guarded_path: str, live: Sequence[FunctionType]) -> FileMode:
    """Swap the mutated file's function bodies into `live`: "swap" when the swap
    applied, "fresh interpreter" when the planner or the live functions refused it
    (nothing is changed then)."""
    with open(guarded_path) as f:
        mutated = f.read()
    try:
        plan = plan_swap(source.clean_source, mutated, source.filename, source.ran_at_import)
    except (SyntaxError, ValueError):
        return FileMode.FRESH_INTERPRETER
    if isinstance(plan, Refusal) or isinstance(plan.apply(live), Refusal):
        return FileMode.FRESH_INTERPRETER
    return FileMode.SWAP


def live_functions_of(guarded_path: str) -> list[FunctionType]:
    """Every live function whose code comes from the guarded file, compared by real path."""
    real = os.path.realpath(guarded_path)
    from_guarded = {guarded_path: True}
    live: list[FunctionType] = []
    for obj in gc.get_objects():
        if not isinstance(obj, FunctionType):
            continue
        filename = obj.__code__.co_filename
        if filename not in from_guarded:
            from_guarded[filename] = os.path.realpath(filename) == real
        if from_guarded[filename]:
            live.append(obj)
    return live


def read_report(read_fd: int) -> bytes:
    """What the child wrote before it ended, closing `read_fd`; never blocks on a
    writer the child left behind (a grandchild that inherited it)."""
    os.set_blocking(read_fd, False)
    try:
        return os.read(read_fd, 64)
    except BlockingIOError:
        return b""
    finally:
        os.close(read_fd)


def report_mode(write_fd: int, mode: str) -> None:
    """Write the child's mode to its report pipe and close it."""
    os.write(write_fd, mode.encode())
    os.close(write_fd)


def reported_mode(report: bytes) -> FileMode:
    """How a child ran its Mutant, from what it wrote to its report pipe. Anything
    else (an empty report included: the child ended before it reported) counts as
    a fresh interpreter, so an in-process run is never claimed unseen."""
    mode = report.decode(errors="replace")
    return FileMode(mode) if mode in _REPORTED_MODES else FileMode.FRESH_INTERPRETER
