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


# mutate4py-manifest-begin
# {"version":1,"tested_at":"2026-06-29T00:35:57Z","module_hash":"7729bdafea54c1bbb36454bbd977bb20d50e287b7bbaeb21baf17fb0ac16b25d","functions":[{"id":"func/function_unit_id","name":"function_unit_id","line":6,"end_line":16,"hash":"76ae22741d38c78927896dfa5deac0ad699693ba9d89ea6ac2260cdf6bb10249"}]}
# mutate4py-manifest-end
