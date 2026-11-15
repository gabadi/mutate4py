"""Shared function-unit ID formatting for manifest and discovery."""

import ast
from collections.abc import Sequence


def function_unit_id(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    parent: ast.AST | None,
    class_names: Sequence[str],
) -> str:
    if isinstance(parent, ast.ClassDef):
        return f"func/{'.'.join(class_names)}.{node.name}"
    return f"func/{node.name}"


def class_unit_id(class_names: Sequence[str]) -> str:
    return f"class/{'.'.join(class_names)}"


def enclosing_class_names(ancestors: Sequence[ast.AST]) -> list[str]:
    return [ancestor.name for ancestor in ancestors if isinstance(ancestor, ast.ClassDef)]


def class_body_unit_id(ancestors: list[ast.AST]) -> str:
    class_names = enclosing_class_names(ancestors)
    return class_unit_id(class_names) if class_names else ""
