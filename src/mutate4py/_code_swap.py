"""Pure planner for swapping mutated code into already-running functions.

`plan_swap` compiles the clean and the mutated source of one guarded file and
decides whether the difference is confined to function bodies that can be
swapped into live function objects. `SwapPlan.apply` performs the swap. Any
other difference is refused with a `Refusal` naming the rule, so the caller can
fall back to a fresh interpreter.

Pure: no I/O and no other mutate4py module (see tach.toml's header).
"""

from __future__ import annotations

import dis
import inspect
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from types import CodeType, FunctionType

__all__ = ["Refusal", "SwapPlan", "plan_swap"]

_NodeKey = tuple[str, int]
_Index = dict[_NodeKey, tuple[CodeType, "_NodeKey | None"]]


@dataclass(frozen=True)
class Refusal:
    """The swap is not safe; `reason` names the rule that refused it."""

    reason: str


@dataclass(frozen=True)
class SwapPlan:
    """Mutated code objects to install over the clean ones they replace."""

    pairs: tuple[tuple[CodeType, CodeType], ...]

    def apply(self, live: Iterable[object]) -> int | Refusal:
        """Point every live function built from a clean code object at its mutant.

        All-or-nothing: each pair must match at least one live function before
        any `__code__` is assigned. Returns the number of functions swapped.
        """
        targets = _targets(self.pairs, _live_functions(live))
        if isinstance(targets, Refusal):
            return targets
        for fn, mutated in targets:
            fn.__code__ = mutated
        return len(targets)


def plan_swap(clean: str, mutated: str, filename: str, ran_at_import: frozenset[int]) -> SwapPlan | Refusal:
    """Plan the swap that turns the clean code of `filename` into the mutated code."""
    before = _index(_compile(clean, filename))
    after = _index(_compile(mutated, filename))
    if _shape(before) != _shape(after):
        return Refusal("shape")
    changed = _changed_keys(before, after)
    tops = _swappable_tops(before, changed)
    refusal = _refusal(before, after, changed, tops, ran_at_import)
    if refusal is not None:
        return refusal
    return SwapPlan(tuple((before[top][0], after[top][0]) for top in tops))


def _changed_keys(before: _Index, after: _Index) -> list[_NodeKey]:
    return [key for key in before if _shallow_key(before[key][0]) != _shallow_key(after[key][0])]


def _swappable_tops(before: _Index, changed: list[_NodeKey]) -> list[_NodeKey]:
    """The functions to swap: each changed function-like node's outermost function, first seen first."""
    return list(dict.fromkeys(_outermost_function(key, before) for key in changed if _function_like(before[key][0])))


def _refusal(
    before: _Index,
    after: _Index,
    changed: list[_NodeKey],
    tops: list[_NodeKey],
    ran_at_import: frozenset[int],
) -> Refusal | None:
    """The first rule the change breaks, or None when the change can be swapped."""
    # A class body can change only because a method's closure changed, so the
    # freevar check runs first and names the root cause.
    if _freevars_changed(before, after, tops):
        return Refusal("freevars")
    if _import_time_changed(before, changed):
        return Refusal("import-time")
    if _body_ran_at_import(before, changed, ran_at_import):
        return Refusal("ran at import")
    return None


def _freevars_changed(before: _Index, after: _Index, tops: list[_NodeKey]) -> bool:
    return any(before[top][0].co_freevars != after[top][0].co_freevars for top in tops)


def _import_time_changed(before: _Index, changed: list[_NodeKey]) -> bool:
    return any(_runs_at_import(before[key][0]) for key in changed)


def _body_ran_at_import(before: _Index, changed: list[_NodeKey], ran_at_import: frozenset[int]) -> bool:
    return any(_body_lines(before[key][0]) & ran_at_import for key in changed)


def _function_like(code: CodeType) -> bool:
    return bool(code.co_flags & inspect.CO_OPTIMIZED)


def _runs_at_import(code: CodeType) -> bool:
    """Module and class bodies run once, at import. Since Python 3.14, annotations
    are evaluated by a function-like `__annotate__` built at import, so that counts too."""
    return not _function_like(code) or code.co_name == "__annotate__"


def _outermost_function(key: _NodeKey, index: _Index) -> _NodeKey:
    """The node a live function must be swapped as: the outermost function-like
    node at or above `key`. A closure has no live object of its own, so its
    enclosing function is replaced instead."""
    top = key
    parent = index[key][1]
    while parent is not None:
        if _function_like(index[parent][0]):
            top = parent
        parent = index[parent][1]
    return top


_PROLOGUE_OPS = frozenset({"RESUME", "MAKE_CELL", "COPY_FREE_VARS"})


def _body_lines(code: CodeType) -> frozenset[int]:
    """Lines holding the function's own statements.

    The prologue sits on the def line, so it is left out. A one-line body shares
    that line and keeps it, because its statement is real body code.
    """
    body = [instruction for instruction in dis.get_instructions(code) if instruction.opname not in _PROLOGUE_OPS]
    lines = {instruction.positions.lineno for instruction in body}
    return frozenset(line for line in lines if line is not None)


def _shape(index: _Index) -> dict[_NodeKey, _NodeKey | None]:
    """Which code objects exist and under which parent, ignoring their contents."""
    return {key: parent for key, (_, parent) in index.items()}


def _compile(source: str, filename: str) -> CodeType:
    """Compile as the guarded file would be: its own __future__ flags, not this module's."""
    return compile(source, filename, "exec", dont_inherit=True)


def _is_live_match(fn: FunctionType, clean: CodeType) -> bool:
    return fn.__code__ == clean and fn.__code__.co_filename == clean.co_filename


def _live_functions(live: Iterable[object]) -> list[FunctionType]:
    return list(dict.fromkeys(obj for obj in live if isinstance(obj, FunctionType)))


def _targets(
    pairs: tuple[tuple[CodeType, CodeType], ...],
    functions: list[FunctionType],
) -> list[tuple[FunctionType, CodeType]] | Refusal:
    """Every live function to swap, or a refusal if any pair has none. Assigns nothing."""
    targets: list[tuple[FunctionType, CodeType]] = []
    for clean, mutated in pairs:
        matches = [fn for fn in functions if _is_live_match(fn, clean)]
        if not matches:
            return Refusal("no live function")
        targets.extend((fn, mutated) for fn in matches)
    return targets


def _index(code: CodeType) -> _Index:
    """Every code object in the tree, keyed by (co_qualname, occurrence) in pre-order."""
    nodes: _Index = {}
    occurrences: Counter[str] = Counter()

    def visit(node: CodeType, parent: _NodeKey | None) -> None:
        key = (node.co_qualname, occurrences[node.co_qualname])
        occurrences[node.co_qualname] += 1
        nodes[key] = (node, parent)
        for const in node.co_consts:
            if isinstance(const, CodeType):
                visit(const, key)

    visit(code, None)
    return nodes


def _shallow_key(code: CodeType) -> tuple:
    """Everything about one code object except the code objects nested in it."""
    return (
        code.co_code,
        code.co_flags,
        code.co_names,
        code.co_varnames,
        code.co_freevars,
        code.co_cellvars,
        code.co_argcount,
        code.co_posonlyargcount,
        code.co_kwonlyargcount,
        code.co_exceptiontable,
        _typed_constants(code.co_consts),
    )


def _typed_constants(consts: tuple) -> tuple:
    """Constants keyed by type and repr, so 1 vs True and 0.0 vs -0.0 differ."""
    return tuple(_typed_constant(const) for const in consts)


def _typed_constant(const: object) -> tuple:
    if isinstance(const, CodeType):
        return (CodeType,)
    if isinstance(const, tuple):
        return (tuple, _typed_constants(const))
    return (type(const), repr(const))
