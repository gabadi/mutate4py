"""Mutation site discovery: AST walk to find all mutable constructs."""

import ast
import dataclasses

from mutate4py._ids import function_unit_id


@dataclasses.dataclass(frozen=True)
class Site:
    index: int
    line: int
    col: int
    function_id: str  # empty string for module-level sites


_ARITH_OPS = {ast.Add, ast.Sub, ast.Mult}
_RELATIONAL_OPS = {ast.Gt, ast.GtE, ast.Lt, ast.LtE}
_EQUALITY_OPS = {ast.Eq, ast.NotEq}
_IDENTITY_OPS = {ast.Is, ast.IsNot}
_MEMBERSHIP_OPS = {ast.In, ast.NotIn}
_COMPARE_OPS = _RELATIONAL_OPS | _EQUALITY_OPS | _IDENTITY_OPS | _MEMBERSHIP_OPS


def _format_function_id(ancestors: list[ast.AST]) -> str:
    """Return the formatted function-unit id for a site, given its ancestor chain.

    Nested def/lambda fold into the outermost enclosing named function unit.
    Method attribution uses the class of that outermost function.
    Returns empty string for module-level code.
    """
    outermost_fn = None
    outermost_idx = -1
    for i, ancestor in enumerate(ancestors):
        if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if outermost_fn is None:
                outermost_fn = ancestor
                outermost_idx = i

    if outermost_fn is None:
        return ""

    parent = ancestors[outermost_idx - 1] if outermost_idx > 0 else None
    return function_unit_id(outermost_fn, parent)


def partition_sites(sites: list[Site], covered_lines: set[int]) -> tuple[int, int]:
    """Return (covered_count, uncovered_count) for the given sites."""
    covered = sum(1 for s in sites if s.line in covered_lines)
    return covered, len(sites) - covered


def discover_sites(source: str) -> list[Site]:
    """Parse source and return all mutation sites, sorted by (line, col)."""
    tree = ast.parse(source)
    raw: list[tuple[int, int, str]] = []
    _walk(tree, raw)
    raw.sort(key=lambda x: (x[0], x[1]))
    return [
        Site(index=i, line=line, col=col, function_id=fid)
        for i, (line, col, fid) in enumerate(raw)
    ]


def _walk(root: ast.AST, sites: list[tuple[int, int, str]]) -> None:
    """Iterative AST traversal; avoids recursion-limit failures on deep trees."""
    stack: list[tuple[ast.AST, list[ast.AST]]] = [(root, [])]
    while stack:
        node, ancestors = stack.pop()
        _classify(node, ancestors, sites)
        next_ancestors = ancestors + [node]
        for child in ast.iter_child_nodes(node):
            stack.append((child, next_ancestors))


def _constant_is_mutable(node: ast.Constant) -> bool:
    if node.value is True or node.value is False:
        return True
    return (
        isinstance(node.value, int)
        and not isinstance(node.value, bool)
        and node.value in (0, 1)
    )


def _is_mutable(node: ast.AST) -> bool:
    if isinstance(node, ast.BinOp):
        return type(node.op) in _ARITH_OPS
    if isinstance(node, ast.Compare):
        return any(type(op) in _COMPARE_OPS for op in node.ops)
    if isinstance(node, ast.BoolOp):
        return True
    if isinstance(node, ast.Constant):
        return _constant_is_mutable(node)
    return False


def _classify(
    node: ast.AST,
    ancestors: list[ast.AST],
    sites: list[tuple[int, int, str]],
) -> None:
    if _is_mutable(node):
        sites.append((node.lineno, node.col_offset, _format_function_id(ancestors)))  # type: ignore[attr-defined]
