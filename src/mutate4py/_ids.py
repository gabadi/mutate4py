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
# {"version":1,"tested_at":"2026-06-29T00:53:58Z","module_hash":"a56f0ba2f383f1a6ce8b92f0bf50b9c8699a02646a69b710beabd9ea3139442e","functions":[{"id":"func/function_unit_id","name":"function_unit_id","line":6,"end_line":16,"hash":"bca4180e4d85d1f91a8eb7b9d49f7b0902ec1458605db7b81aab567c8714f5ec"}]}
# mutate4py-manifest-end
