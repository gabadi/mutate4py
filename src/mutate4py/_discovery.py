"""Mutation site discovery: AST walk to find all mutable constructs."""

import ast
import dataclasses


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

_BOOL_OPS = {ast.And, ast.Or}

_EXCLUDED_AUGASSIGN_OPS = {ast.Add, ast.Sub}


def _enclosing_function_id(node: ast.AST, ancestors: list[ast.AST]) -> str:
    """Find the enclosing named function unit for a site.

    Nested def/lambda fold into the outermost enclosing named function unit.
    Method attribution uses the class of that outermost function.
    Returns empty string for module-level code.
    """
    # Find the outermost (first) named function/async-def in ancestors
    outermost_fn = None
    outermost_idx = -1
    for i, ancestor in enumerate(ancestors):
        if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if outermost_fn is None:
                outermost_fn = ancestor
                outermost_idx = i

    if outermost_fn is None:
        return ""

    # Check if this outermost function is a method (parent is ClassDef)
    parent = ancestors[outermost_idx - 1] if outermost_idx > 0 else None
    if isinstance(parent, ast.ClassDef):
        return f"func/{parent.name}.{outermost_fn.name}"
    return f"func/{outermost_fn.name}"


def discover_sites(source: str) -> list[Site]:
    """Parse source and return all mutation sites, sorted by (line, col)."""
    tree = ast.parse(source)
    raw: list[tuple[int, int, str]] = []  # (line, col, function_id)
    _walk(tree, [], raw)
    raw.sort(key=lambda x: (x[0], x[1]))
    return [
        Site(index=i, line=line, col=col, function_id=fid)
        for i, (line, col, fid) in enumerate(raw)
    ]


def _walk(
    node: ast.AST, ancestors: list[ast.AST], sites: list[tuple[int, int, str]]
) -> None:
    if isinstance(node, ast.BinOp):
        op = node.op
        if type(op) in _ARITH_OPS:
            sites.append(
                (node.lineno, node.col_offset, _enclosing_function_id(node, ancestors))
            )
        # / is excluded; * is catalogued (* → /)

    elif isinstance(node, ast.Compare):
        for op in node.ops:
            t = type(op)
            if (
                t in _RELATIONAL_OPS
                or t in _EQUALITY_OPS
                or t in _IDENTITY_OPS
                or t in _MEMBERSHIP_OPS
            ):
                sites.append(
                    (
                        node.lineno,
                        node.col_offset,
                        _enclosing_function_id(node, ancestors),
                    )
                )
                break  # one site per Compare node

    elif isinstance(node, ast.BoolOp):
        if type(node.op) in _BOOL_OPS:
            sites.append(
                (node.lineno, node.col_offset, _enclosing_function_id(node, ancestors))
            )

    elif isinstance(node, ast.Constant):
        if node.value is True or node.value is False:
            sites.append(
                (node.lineno, node.col_offset, _enclosing_function_id(node, ancestors))
            )
        elif (
            isinstance(node.value, int)
            and not isinstance(node.value, bool)
            and node.value in (0, 1)
        ):
            sites.append(
                (node.lineno, node.col_offset, _enclosing_function_id(node, ancestors))
            )

    # AugAssign (+=, -=, etc.) is explicitly excluded — no site emitted
    # Unary ops excluded — no site emitted
    # / operator excluded — no site emitted
    # integers other than 0 and 1 excluded — no site emitted

    new_ancestors = ancestors + [node]
    for child in ast.iter_child_nodes(node):
        _walk(child, new_ancestors, sites)
