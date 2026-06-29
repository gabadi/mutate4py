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
# {"version":1,"tested_at":"2026-06-29T00:35:57Z","module_hash":"dd6eb9f31440b12e317bf2a7d784d0be17579db6eba796b729cbe066d97d21a3","functions":[{"id":"func/_format_function_id","name":"_format_function_id","line":55,"end_line":74,"hash":"eb3b2d05b2556103e441786877805ae9ae342880b45f846c2c588c923a45f576"},{"id":"func/_build_line_index","name":"_build_line_index","line":77,"end_line":83,"hash":"4701b367360e4097f32f5bd4018811fc9b75233e9ffb950349b13c397fc8583e"},{"id":"func/_abs_offset","name":"_abs_offset","line":86,"end_line":88,"hash":"2aeb5a367819686533864ec3a43d516fd03c5495956d62c8a4ef8652d8d9a2af"},{"id":"func/_node_text","name":"_node_text","line":91,"end_line":95,"hash":"145d30124cbd6836a1292446293b30ba7e281e223f40971e1c521656f3f6b30c"},{"id":"func/_replace_op_token","name":"_replace_op_token","line":98,"end_line":101,"hash":"6d1d624552bf9e82ff8da910f054984e47eff8da8d1615f115e353f67b4f339d"},{"id":"func/_mutate_binop","name":"_mutate_binop","line":104,"end_line":125,"hash":"adb7b882b52ada8b2a339e7c3743a2644292676d1355cd57fe0448ddc0c556cb"},{"id":"func/_mutate_compare","name":"_mutate_compare","line":128,"end_line":153,"hash":"78c4295287471a6241a4e4689eda50c9f173e1dbc5f5d81994b09c4680496721"},{"id":"func/_mutate_boolop","name":"_mutate_boolop","line":156,"end_line":181,"hash":"4ca038f33849ed58986ae71a15be34254dbd79107de4107d587547403a3bf6ff"},{"id":"func/_mutate_int_constant","name":"_mutate_int_constant","line":184,"end_line":189,"hash":"d72ea5093af8d1702352326de71024ffcfe4e20b6c58765e490eb0af4cec03f9"},{"id":"func/_mutate_constant","name":"_mutate_constant","line":192,"end_line":200,"hash":"7c5c8bb427d4a24fd01adff789674d8dae2dc7df7c8347b84f808d9a03e97faf"},{"id":"func/apply_mutant","name":"apply_mutant","line":203,"end_line":208,"hash":"654b91f4a7753f9ee2a31aa79e690b46bbe09571e9f3f09a2a2e33750e3b41ae"},{"id":"func/partition_sites","name":"partition_sites","line":211,"end_line":214,"hash":"0a6754c42d300a86b23733e4dc5cedc677845d5fb2058a00e23f74a1fc0ca9e8"},{"id":"func/discover_sites","name":"discover_sites","line":217,"end_line":237,"hash":"f5acc18aa59d5942feddd5619f2f1210bfbfd630017739a527098197379ab27e"},{"id":"func/_walk","name":"_walk","line":240,"end_line":253,"hash":"8b0337b20a41b3c0bd8108754cedc7c3de6fa6d52e3f26a595111694bd0a83c2"},{"id":"func/_constant_is_mutable","name":"_constant_is_mutable","line":256,"end_line":263,"hash":"67eb17d4d74bcaad6364c18db451a49330dc90eb63429deda73f65924bcdb9fe"},{"id":"func/_is_mutable","name":"_is_mutable","line":266,"end_line":275,"hash":"0b2c5ce0024e83d244d4f95bbface73a91f79baa683c226593754f5b634b2767"},{"id":"func/_dispatch_mutation","name":"_dispatch_mutation","line":278,"end_line":291,"hash":"f7abe217cc03c6c14c819b256e60b2bd250f9a35b602c27cf8428e985b64dc64"},{"id":"func/_classify","name":"_classify","line":294,"end_line":318,"hash":"b004fc9d64025de0286c9313624741a92b28f3965487b1d7eb09d36a2c77b2cb"}]}
# mutate4py-manifest-end
