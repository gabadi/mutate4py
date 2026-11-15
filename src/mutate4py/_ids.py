"""Shared function-unit ID formatting for manifest and discovery."""

import ast
from collections.abc import Sequence


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


def class_unit_id(class_names: Sequence[str]) -> str:
    return f"class/{'.'.join(class_names)}"


def class_body_unit_id(ancestors: list[ast.AST]) -> str:
    class_names = [ancestor.name for ancestor in ancestors if isinstance(ancestor, ast.ClassDef)]
    return class_unit_id(class_names) if class_names else ""
