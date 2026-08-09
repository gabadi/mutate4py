"""Shared function-unit ID formatting for manifest and discovery."""

import ast


def function_unit_id(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    parent: ast.AST | None,
) -> str:
    """Return the canonical function-unit id for a named function node.

    Method attribution uses the immediately enclosing ClassDef.
    """
    if isinstance(parent, ast.ClassDef):
        return f"func/{parent.name}.{node.name}"
    return f"func/{node.name}"
