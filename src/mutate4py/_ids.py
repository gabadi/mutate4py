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
# {"version":1,"tested_at":"2026-06-29T05:03:13Z","module_hash":"8e3a6461a8b8c2a37dbdac33268650bc3c74ff2db0949641b3e97a94d6b310c8","functions":[{"id":"func/function_unit_id","name":"function_unit_id","line":6,"end_line":16,"hash":"cd7db1047a88c7306b9e5d4769090de1665329ead7a6b9449756562491ee73c1"}]}
# mutate4py-manifest-end
