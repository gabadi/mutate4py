import ast
import copy
import hashlib

from mutate4py._ids import class_unit_id, function_unit_id

__all__ = ["ast_sha256", "extract_units"]

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_DEFINITIONS = (*_FUNCTIONS, ast.ClassDef)


def ast_sha256(node: ast.AST) -> str:
    return hashlib.sha256(ast.unparse(node).encode()).hexdigest()


def _class_body(node: ast.ClassDef) -> ast.ClassDef:
    body = copy.copy(node)
    body.body = [statement for statement in node.body if not isinstance(statement, _DEFINITIONS)]
    return body


def _unit(unit_id: str, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef, unit_hash: str) -> dict:
    return {"id": unit_id, "name": node.name, "line": node.lineno, "end_line": node.end_lineno, "hash": unit_hash}


def _own_unit(node: ast.AST, parent: ast.AST | None, *, inside_fn: bool, class_names: tuple[str, ...]) -> dict | None:
    if inside_fn:
        return None
    if isinstance(node, _FUNCTIONS):
        return _unit(function_unit_id(node, parent), node, ast_sha256(node))
    if isinstance(node, ast.ClassDef):
        return _unit(class_unit_id((*class_names, node.name)), node, ast_sha256(_class_body(node)))
    return None


def extract_units(tree: ast.Module) -> list[dict]:
    results = []
    stack: list[tuple[ast.AST, ast.AST | None, bool, tuple[str, ...]]] = [(tree, None, False, ())]
    while stack:
        node, parent, inside_fn, class_names = stack.pop()
        unit = _own_unit(node, parent, inside_fn=inside_fn, class_names=class_names)
        if unit is not None:
            results.append(unit)
        inside_child = inside_fn or isinstance(node, _FUNCTIONS)
        child_class_names = (*class_names, node.name) if isinstance(node, ast.ClassDef) else class_names
        for child in ast.iter_child_nodes(node):
            stack.append((child, node, inside_child, child_class_names))
    results.sort(key=lambda unit: unit["line"])
    return results
