import ast
import copy
import hashlib

from mutate4py._ids import class_unit_id, function_unit_id

__all__ = ["ast_sha256", "extract_units"]

_DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def ast_sha256(node: ast.AST) -> str:
    return hashlib.sha256(ast.unparse(node).encode()).hexdigest()


def _class_body(node: ast.ClassDef) -> ast.ClassDef:
    body = copy.copy(node)
    body.body = [statement for statement in node.body if not isinstance(statement, _DEFINITIONS)]
    return body


def _unit(unit_id: str, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef, unit_hash: str) -> dict:
    return {"id": unit_id, "name": node.name, "line": node.lineno, "end_line": node.end_lineno, "hash": unit_hash}


def extract_units(tree: ast.Module) -> list[dict]:
    results = []
    stack: list[tuple[ast.AST, ast.AST | None, bool]] = [(tree, None, False)]
    while stack:
        node, parent, inside_fn = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not inside_fn:
                results.append(_unit(function_unit_id(node, parent), node, ast_sha256(node)))
            inside_fn = True
        elif isinstance(node, ast.ClassDef) and not inside_fn:
            results.append(_unit(class_unit_id(node), node, ast_sha256(_class_body(node))))
        for child in ast.iter_child_nodes(node):
            stack.append((child, node, inside_fn))
    results.sort(key=lambda unit: unit["line"])
    return results
