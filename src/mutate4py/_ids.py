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


def class_unit_id(node: ast.ClassDef) -> str:
    return f"class/{node.name}"


def class_body_unit_id(ancestors: list[ast.AST]) -> str:
    for ancestor in reversed(ancestors):
        if isinstance(ancestor, ast.ClassDef):
            return class_unit_id(ancestor)
    return ""
