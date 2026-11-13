"""What a swap-mode child of the forking executor does before pytest starts,
kept out of the fork plumbing so it can be tested in-process.

The fork server primed a guarded file that prime itself imported (a conftest
or a plugin did), so every forked child holds the clean module. `swap_in`
plans the body swap from the clean source to the mutated file on disk
(`_code_swap.plan_swap`) and applies it to the live functions prime built.
Any refusal means the Mutant runs in a fresh interpreter instead. The child
reports which through a pipe; `read_report` and `swap_child_mode` turn that
back into the mode `describe` counts.
"""

import dataclasses
import gc
import os
from collections.abc import Sequence
from types import FunctionType

from mutate4py._code_swap import Refusal, plan_swap

__all__ = ["SwapSource", "live_functions_of", "read_report", "swap_child_mode", "swap_in"]


@dataclasses.dataclass(frozen=True)
class SwapSource:
    """The clean side of every swap: the guarded file's source as prime saw it, the
    filename its live code was compiled under, and the lines the Measurement saw
    run under the Empty context (a changed body among them ran at import)."""

    clean_source: str
    filename: str
    ran_at_import: frozenset[int]


def swap_in(source: SwapSource, guarded_path: str, live: Sequence[FunctionType]) -> str:
    """Swap the mutated file's function bodies into `live`: "swap" when the swap
    applied, "fresh interpreter" when the planner or the live functions refused it
    (nothing is changed then)."""
    with open(guarded_path) as f:
        mutated = f.read()
    try:
        plan = plan_swap(source.clean_source, mutated, source.filename, source.ran_at_import)
    except (SyntaxError, ValueError):
        return "fresh interpreter"
    if isinstance(plan, Refusal) or isinstance(plan.apply(live), Refusal):
        return "fresh interpreter"
    return "swap"


def live_functions_of(guarded_path: str) -> list[FunctionType]:
    """Every live function whose code comes from the guarded file, compared by real path."""
    real = os.path.realpath(guarded_path)
    return [
        obj
        for obj in gc.get_objects()
        if isinstance(obj, FunctionType) and os.path.realpath(obj.__code__.co_filename) == real
    ]


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


def swap_child_mode(report: bytes) -> str:
    """How a swap-mode child ran its Mutant, from what it wrote to its report pipe.
    Anything but "swap" (an empty report included: the child ended before it
    reported) counts as a fresh interpreter, so a swap is never claimed unseen."""
    return "swap" if report == b"swap" else "fresh interpreter"
