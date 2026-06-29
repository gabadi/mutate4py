"""Mutation site discovery: AST walk to find all mutable constructs."""

import ast
import dataclasses

from mutate4py._ids import function_unit_id


@dataclasses.dataclass(frozen=True)
class Site:
    index: int
    line: int
    col: int
    end_line: int
    end_col: int
    function_id: str  # empty string for module-level sites
    orig_text: str  # original source text of the mutable node
    mutant_text: str  # mutated replacement text
    desc: str  # "<orig_text> -> <mutant_text>"


_ARITH_OPS = {ast.Add, ast.Sub, ast.Mult}
_RELATIONAL_OPS = {ast.Gt, ast.GtE, ast.Lt, ast.LtE}
_EQUALITY_OPS = {ast.Eq, ast.NotEq}
_IDENTITY_OPS = {ast.Is, ast.IsNot}
_MEMBERSHIP_OPS = {ast.In, ast.NotIn}
_COMPARE_OPS = _RELATIONAL_OPS | _EQUALITY_OPS | _IDENTITY_OPS | _MEMBERSHIP_OPS

# Operator text tokens (original -> mutant)
_ARITH_TOKEN_MUTATIONS: dict[type, tuple[str, str]] = {
    ast.Add: ("+", "-"),
    ast.Sub: ("-", "+"),
    ast.Mult: ("*", "/"),
}

_COMPARE_TOKEN_MUTATIONS: dict[type, tuple[str, str]] = {
    ast.Gt: (">", ">="),
    ast.GtE: (">=", ">"),
    ast.Lt: ("<", "<="),
    ast.LtE: ("<=", "<"),
    ast.Eq: ("==", "!="),
    ast.NotEq: ("!=", "=="),
    ast.Is: ("is", "is not"),
    ast.IsNot: ("is not", "is"),
    ast.In: ("in", "not in"),
    ast.NotIn: ("not in", "in"),
}

_BOOL_OP_TOKEN_MUTATIONS: dict[type, tuple[str, str]] = {
    ast.And: ("and", "or"),
    ast.Or: ("or", "and"),
}


def _format_function_id(ancestors: list[ast.AST]) -> str:
    """Return the formatted function-unit id for a site, given its ancestor chain.

    Nested def/lambda fold into the outermost enclosing named function unit.
    Method attribution uses the class of that outermost function.
    Returns empty string for module-level code.
    """
    outermost_fn = None
    outermost_idx = -1
    for i, ancestor in enumerate(ancestors):
        if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if outermost_fn is None:
                outermost_fn = ancestor
                outermost_idx = i

    if outermost_fn is None:
        return ""

    parent = ancestors[outermost_idx - 1] if outermost_idx > 0 else None
    return function_unit_id(outermost_fn, parent)


def _build_line_index(source: str) -> list[int]:
    """Return list of character offsets for each line start (0-indexed lines → 1-indexed lines)."""
    offsets = [0]
    for i, ch in enumerate(source):
        if ch == "\n":
            offsets.append(i + 1)
    return offsets


def _abs_offset(line_index: list[int], lineno: int, col_offset: int) -> int:
    """Convert 1-based lineno + 0-based col_offset to absolute character offset."""
    return line_index[lineno - 1] + col_offset


def _node_text(source: str, line_index: list[int], node: ast.AST) -> str:
    """Extract source text for a node using its span attributes."""
    start = _abs_offset(line_index, node.lineno, node.col_offset)  # type: ignore[attr-defined]
    end = _abs_offset(line_index, node.end_lineno, node.end_col_offset)  # type: ignore[attr-defined]
    return source[start:end]


def _replace_op_token(node_text: str, orig_op: str, mutant_op: str) -> str:
    """Replace the first occurrence of orig_op (as whole token) in node_text."""
    # For multi-char ops or keyword ops, replace the first match
    return node_text.replace(orig_op, mutant_op, 1)


def _mutate_binop(
    source: str, line_index: list[int], node: ast.BinOp
) -> tuple[str, str] | None:
    """Return (orig_text, mutant_text) for a BinOp mutation, or None."""
    token_pair = _ARITH_TOKEN_MUTATIONS.get(type(node.op))
    if token_pair is None:
        return None
    orig_op, mutant_op = token_pair
    orig = _node_text(source, line_index, node)
    # The operator is between left.end and right.start; replace its token in node text
    left_end = _abs_offset(line_index, node.left.end_lineno, node.left.end_col_offset)  # type: ignore[attr-defined]
    right_start = _abs_offset(line_index, node.right.lineno, node.right.col_offset)  # type: ignore[attr-defined]
    node_start = _abs_offset(line_index, node.lineno, node.col_offset)  # type: ignore[attr-defined]
    between = source[left_end:right_start]
    # Replace op token in the between-region
    new_between = between.replace(orig_op, mutant_op, 1)
    if new_between == between:
        return None
    rel_left_end = left_end - node_start
    rel_right_start = right_start - node_start
    mutant = orig[:rel_left_end] + new_between + orig[rel_right_start:]
    return orig, mutant


def _mutate_compare(
    source: str, line_index: list[int], node: ast.Compare
) -> tuple[str, str] | None:
    """Return (orig_text, mutant_text) for first mutable Compare op, or None."""
    # Pairs: (left_node, op, right_node)
    lefts = [node.left] + list(node.comparators[:-1])
    for left_node, op, right_node in zip(lefts, node.ops, node.comparators):
        token_pair = _COMPARE_TOKEN_MUTATIONS.get(type(op))
        if token_pair is None:
            continue
        orig_op, mutant_op = token_pair
        orig = _node_text(source, line_index, node)
        left_end = _abs_offset(
            line_index, left_node.end_lineno, left_node.end_col_offset
        )  # type: ignore[attr-defined]
        right_start = _abs_offset(line_index, right_node.lineno, right_node.col_offset)  # type: ignore[attr-defined]
        node_start = _abs_offset(line_index, node.lineno, node.col_offset)  # type: ignore[attr-defined]
        between = source[left_end:right_start]
        new_between = between.replace(orig_op, mutant_op, 1)
        if new_between == between:
            continue
        rel_left_end = left_end - node_start
        rel_right_start = right_start - node_start
        mutant = orig[:rel_left_end] + new_between + orig[rel_right_start:]
        return orig, mutant
    return None


def _mutate_boolop(
    source: str, line_index: list[int], node: ast.BoolOp
) -> tuple[str, str] | None:
    """Return (orig_text, mutant_text) for a BoolOp mutation, or None."""
    token_pair = _BOOL_OP_TOKEN_MUTATIONS.get(type(node.op))
    if token_pair is None:
        return None
    orig_op, mutant_op = token_pair
    orig = _node_text(source, line_index, node)
    # Find the operator between first and second values
    first_end = _abs_offset(
        line_index, node.values[0].end_lineno, node.values[0].end_col_offset
    )  # type: ignore[attr-defined]
    second_start = _abs_offset(
        line_index, node.values[1].lineno, node.values[1].col_offset
    )  # type: ignore[attr-defined]
    node_start = _abs_offset(line_index, node.lineno, node.col_offset)  # type: ignore[attr-defined]
    between = source[first_end:second_start]
    # Replace " and " or " or " with space-padded mutant
    new_between = between.replace(orig_op, mutant_op, 1)
    if new_between == between:
        return None
    rel_first_end = first_end - node_start
    rel_second_start = second_start - node_start
    mutant = orig[:rel_first_end] + new_between + orig[rel_second_start:]
    return orig, mutant


def _mutate_int_constant(value: int) -> tuple[str, str] | None:
    if value == 0:
        return "0", "1"
    if value == 1:
        return "1", "0"
    return None


def _mutate_constant(node: ast.Constant) -> tuple[str, str] | None:
    """Return (orig_text, mutant_text) for a Constant mutation, or None."""
    if node.value is True:
        return "True", "False"
    if node.value is False:
        return "False", "True"
    if isinstance(node.value, int) and not isinstance(node.value, bool):
        return _mutate_int_constant(node.value)
    return None


def apply_mutant(source: str, site: Site) -> str:
    """Return source with the site's mutation spliced in."""
    line_index = _build_line_index(source)
    start = _abs_offset(line_index, site.line, site.col)
    end = _abs_offset(line_index, site.end_line, site.end_col)
    return source[:start] + site.mutant_text + source[end:]


def partition_sites(sites: list[Site], covered_lines: set[int]) -> tuple[int, int]:
    """Return (covered_count, uncovered_count) for the given sites."""
    covered = sum(1 for s in sites if s.line in covered_lines)
    return covered, len(sites) - covered


def discover_sites(source: str) -> list[Site]:
    """Parse source and return all mutation sites, sorted by (line, col)."""
    tree = ast.parse(source)
    line_index = _build_line_index(source)
    raw: list[tuple[int, int, int, int, str, str, str]] = []
    _walk(tree, source, line_index, raw)
    raw.sort(key=lambda x: (x[0], x[1]))
    return [
        Site(
            index=i,
            line=line,
            col=col,
            end_line=end_line,
            end_col=end_col,
            function_id=fid,
            orig_text=orig,
            mutant_text=mutant,
            desc=f"{orig} -> {mutant}",
        )
        for i, (line, col, end_line, end_col, fid, orig, mutant) in enumerate(raw)
    ]


def _walk(
    root: ast.AST,
    source: str,
    line_index: list[int],
    sites: list[tuple[int, int, int, int, str, str, str]],
) -> None:
    """Iterative AST traversal; avoids recursion-limit failures on deep trees."""
    stack: list[tuple[ast.AST, list[ast.AST]]] = [(root, [])]
    while stack:
        node, ancestors = stack.pop()
        _classify(node, ancestors, source, line_index, sites)
        next_ancestors = ancestors + [node]
        for child in ast.iter_child_nodes(node):
            stack.append((child, next_ancestors))


def _constant_is_mutable(node: ast.Constant) -> bool:
    if node.value is True or node.value is False:
        return True
    return (
        isinstance(node.value, int)
        and not isinstance(node.value, bool)
        and node.value in (0, 1)
    )


def _is_mutable(node: ast.AST) -> bool:
    if isinstance(node, ast.BinOp):
        return type(node.op) in _ARITH_OPS
    if isinstance(node, ast.Compare):
        return any(type(op) in _COMPARE_OPS for op in node.ops)
    if isinstance(node, ast.BoolOp):
        return True
    if isinstance(node, ast.Constant):
        return _constant_is_mutable(node)
    return False


def _dispatch_mutation(
    node: ast.AST,
    source: str,
    line_index: list[int],
) -> tuple[str, str] | None:
    if isinstance(node, ast.BinOp):
        return _mutate_binop(source, line_index, node)
    if isinstance(node, ast.Compare):
        return _mutate_compare(source, line_index, node)
    if isinstance(node, ast.BoolOp):
        return _mutate_boolop(source, line_index, node)
    if isinstance(node, ast.Constant):
        return _mutate_constant(node)
    return None


def _classify(
    node: ast.AST,
    ancestors: list[ast.AST],
    source: str,
    line_index: list[int],
    sites: list[tuple[int, int, int, int, str, str, str]],
) -> None:
    if not _is_mutable(node):
        return
    mutation = _dispatch_mutation(node, source, line_index)
    if mutation is None:
        return
    fid = _format_function_id(ancestors)
    orig, mutant = mutation
    sites.append(
        (
            node.lineno,  # type: ignore[attr-defined]
            node.col_offset,  # type: ignore[attr-defined]
            node.end_lineno,  # type: ignore[attr-defined]
            node.end_col_offset,  # type: ignore[attr-defined]
            fid,
            orig,
            mutant,
        )
    )


# mutate4py-manifest-begin
# {"version":1,"tested_at":"2026-06-29T00:53:58Z","module_hash":"dd7769d7fdc87349175b2dcd26f2982743708ae231cd43ec47b8a997d0944a22","functions":[{"id":"func/_format_function_id","name":"_format_function_id","line":55,"end_line":74,"hash":"069ddefc0bf66b0a0db067c4c6dded6c37afe94f650f00268db988e029ec1dc2"},{"id":"func/_build_line_index","name":"_build_line_index","line":77,"end_line":83,"hash":"accc024e95646968dcb9252ecb12aa59932283a6b583f09e3e2bbc82d3903a46"},{"id":"func/_abs_offset","name":"_abs_offset","line":86,"end_line":88,"hash":"028fac5f44e1df755122a69717e4e44bc37f7cab6d3a80260bb3175c4436b02b"},{"id":"func/_node_text","name":"_node_text","line":91,"end_line":95,"hash":"bf9834be2539313c669aacf90b4f662b02f301833569c26b72f5fbd516a2f65f"},{"id":"func/_replace_op_token","name":"_replace_op_token","line":98,"end_line":101,"hash":"993e2202dc3b2378a8412902f954f672d788d82303d80d4e1eb310137d72da8e"},{"id":"func/_mutate_binop","name":"_mutate_binop","line":104,"end_line":125,"hash":"7d6133d4e6e0dd4e116f3716c41449eead042ca1415232e02e8437568b831537"},{"id":"func/_mutate_compare","name":"_mutate_compare","line":128,"end_line":153,"hash":"f9e69b891120bb507acc6b9debd12767ded1d5f9ad498b7162715d55194abba9"},{"id":"func/_mutate_boolop","name":"_mutate_boolop","line":156,"end_line":181,"hash":"d7409cd5eadbabe3d8780c6a855cf28400cb302f47169aff008b7cf757210147"},{"id":"func/_mutate_int_constant","name":"_mutate_int_constant","line":184,"end_line":189,"hash":"05851d954c4205da547f50f7eb50e22897576b73d5ee3f0c3470ede118886ee8"},{"id":"func/_mutate_constant","name":"_mutate_constant","line":192,"end_line":200,"hash":"a657bb86ff54a8a1c804b50035f9075fc8acde1447ec6fa28ad2b062bcb85e0d"},{"id":"func/apply_mutant","name":"apply_mutant","line":203,"end_line":208,"hash":"989e67c5454c7c17efee93e8aee82c3f6a17cb245dcfa87e659ae80b3714bf31"},{"id":"func/partition_sites","name":"partition_sites","line":211,"end_line":214,"hash":"9609ca41558793e8506743eb86eb1a38c0f12f2464d57628b4c83aef2b1163ac"},{"id":"func/discover_sites","name":"discover_sites","line":217,"end_line":237,"hash":"734b124f8ad6a6c858cb7d5ddc2a671742342d306cb209197ad611bd43a8c523"},{"id":"func/_walk","name":"_walk","line":240,"end_line":253,"hash":"10d3728a561c75819bd73a31fec45ab0d34271c3f9c457746b6f64c4b2ec0d4e"},{"id":"func/_constant_is_mutable","name":"_constant_is_mutable","line":256,"end_line":263,"hash":"14ed83e6400b6687f1d7734158bb083f52137d4c8cd14213895a448a355cf2a8"},{"id":"func/_is_mutable","name":"_is_mutable","line":266,"end_line":275,"hash":"8094564b48c1d7eea357b148bfe2c4afa8c996f86929ffbae4d0fea1c57f3b7e"},{"id":"func/_dispatch_mutation","name":"_dispatch_mutation","line":278,"end_line":291,"hash":"65d4984bdad84bc2defaa4a5a5cdd0ba635717b75d74127e933a8c5b9a323aae"},{"id":"func/_classify","name":"_classify","line":294,"end_line":318,"hash":"7901c8029ca55589963791ced2df8b39d3598ffb11e1cafcd0695bcf88a6d5da"}]}
# mutate4py-manifest-end
