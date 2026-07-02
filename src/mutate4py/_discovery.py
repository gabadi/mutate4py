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
# {"version":1,"tested_at":"2026-07-02T01:49:52Z","module_hash":"e52ed78d90736c991dc284de843e35758863d97bb591cd168ebb6dc6d835d3d3","functions":[{"id":"func/_format_function_id","name":"_format_function_id","line":55,"end_line":74,"hash":"06ac0709c392bf86bcf433a9f0156ea03f3678580e128e45235f89f04e72813c"},{"id":"func/_build_line_index","name":"_build_line_index","line":77,"end_line":83,"hash":"f4d73a9a6cf58134ce39a4f68bf7fccf461f1b97cccc5014b3e1f344076a7bb1"},{"id":"func/_abs_offset","name":"_abs_offset","line":86,"end_line":88,"hash":"499042bfdd1ae5af7fa0e59bca146e1c68e8137a7315f458c0b5ecd7dd29ed5c"},{"id":"func/_node_text","name":"_node_text","line":91,"end_line":95,"hash":"4761252a9a5156047e7705f5f44914e7a49d6601005ed3ee1deb629f62e4de75"},{"id":"func/_replace_op_token","name":"_replace_op_token","line":98,"end_line":101,"hash":"e42f2a3f5e08c3c459572580217a177b9bd7616cecc973a1eb867d9942be4990"},{"id":"func/_mutate_binop","name":"_mutate_binop","line":104,"end_line":125,"hash":"821e1c387d82079b3b7fbe3f1e34c3af099ba737068dd139011279bb40f071f4"},{"id":"func/_mutate_compare","name":"_mutate_compare","line":128,"end_line":153,"hash":"f5f2a6f5dffdf3104344aecc6b48227810f26a68f2b0c6a80fb2a63d16540c33"},{"id":"func/_mutate_boolop","name":"_mutate_boolop","line":156,"end_line":181,"hash":"27f85220bb13cffd0e14d4dffe1634b9b94a2e797ed5a285ef2f911f44f8fe6b"},{"id":"func/_mutate_int_constant","name":"_mutate_int_constant","line":184,"end_line":189,"hash":"862aeb31bb0398db7991d3518303b7f15a824a494ba37b3f0f50235d258fe9ca"},{"id":"func/_mutate_constant","name":"_mutate_constant","line":192,"end_line":200,"hash":"fc08c8c10ca6fbbb71dc83a3817dc7165dabb8ab3ff74fe1380f4dd98e5cf173"},{"id":"func/apply_mutant","name":"apply_mutant","line":203,"end_line":208,"hash":"04034125ba80dc15b0b57048549415c4728b947ebf445f3906c670d6f1aad459"},{"id":"func/partition_sites","name":"partition_sites","line":211,"end_line":214,"hash":"8d4f8aa918751b9adec86597ccef52a8cf5e945461fe89ead98d842c0cb45793"},{"id":"func/discover_sites","name":"discover_sites","line":217,"end_line":237,"hash":"9693afe2da9df505c30d8e4ebd24b30a315e13fe7e22ddbccca3c46da1dd7df2"},{"id":"func/_walk","name":"_walk","line":240,"end_line":253,"hash":"0740d0eb8d1c16cb9c4a5189378e7b8ab601ae7ae2d6f1f44a9685dd00ce48b7"},{"id":"func/_constant_is_mutable","name":"_constant_is_mutable","line":256,"end_line":263,"hash":"8bd89418a31200648d884abe84d2de354d7c5bf92a4835982395362db67d0913"},{"id":"func/_is_mutable","name":"_is_mutable","line":266,"end_line":275,"hash":"5e0281e3de16a7546103f2adcd905cd8ec4c5d726d2f872f17237b55bea5f8b1"},{"id":"func/_dispatch_mutation","name":"_dispatch_mutation","line":278,"end_line":291,"hash":"a7abc85e386b1fef306a987d74adbc0217bd33761ee5b2d2eab2188626ba0570"},{"id":"func/_classify","name":"_classify","line":294,"end_line":318,"hash":"0d0e008fffde3b863574dc9a8009ef6525ed7d32f7dabd606a41722c8117116d"}]}
# mutate4py-manifest-end
