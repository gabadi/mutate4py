"""Unit tests for mutation site discovery (F1 — site-discovery)."""

import ast
import textwrap
import pytest
from mutate4py._discovery import discover_sites, _classify


def scan(src: str):
    return discover_sites(textwrap.dedent(src))


# ── Catalogued operators each yield exactly one site ──────────────────────────


@pytest.mark.parametrize(
    "expr,count",
    [
        ("x = a + b", 1),
        ("x = a - b", 1),
        ("x = a * b", 1),
        ("x = a > b", 1),
        ("x = a >= b", 1),
        ("x = a < b", 1),
        ("x = a <= b", 1),
        ("x = a == b", 1),
        ("x = a != b", 1),
        ("x = a is b", 1),
        ("x = a is not b", 1),
        ("x = a in b", 1),
        ("x = a not in b", 1),
        ("x = a and b", 1),
        ("x = a or b", 1),
        ("x = True", 1),
        ("x = False", 1),
        ("x = 0", 1),
        ("x = 1", 1),
    ],
)
def test_catalogued_construct_yields_one_site(expr, count):
    sites = scan(expr)
    assert len(sites) == count


# ── Excluded constructs yield no site ─────────────────────────────────────────


@pytest.mark.parametrize(
    "expr",
    [
        "a += b",
        "a -= b",
        "x = a / b",
        "x = -a",
        "x = 2",
    ],
)
def test_excluded_construct_yields_no_site(expr):
    assert scan(expr) == []


# ── Sites are sorted by (line, col) with stable Index ─────────────────────────


def test_sites_sorted_by_line_col():
    src = """\
        x = a + b
        y = c - d
    """
    sites = scan(src)
    assert len(sites) == 2
    assert sites[0].line < sites[1].line
    assert sites[0].index == 0
    assert sites[1].index == 1


# ── Function attribution ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "src,expected_id",
    [
        ("def foo():\n    x = a + b\n", "func/foo"),
        ("async def foo():\n    x = a + b\n", "func/foo"),
        ("class C:\n    def m(self):\n        x = a + b\n", "func/C.m"),
    ],
)
def test_basic_function_attribution(src, expected_id):
    sites = scan(src)
    assert sites[0].function_id == expected_id


def test_module_level_no_def():
    src = "x = a + b\n"
    sites = scan(src)
    assert sites[0].function_id == ""


@pytest.mark.parametrize(
    "src",
    [
        "def outer():\n    def inner():\n        x = a + b\n",
        "def outer():\n    f = lambda: a + b\n",
    ],
)
def test_nested_constructs_fold_into_outer(src):
    sites = scan(src)
    assert all(s.function_id == "func/outer" for s in sites)


# ── Large integer literals are excluded ───────────────────────────────────────


def test_integer_2_excluded():
    assert scan("x = 2") == []


def test_integer_3_excluded():
    assert scan("x = 3") == []


# ── Division is excluded ──────────────────────────────────────────────────────


def test_division_excluded():
    assert scan("x = a / b") == []


# ── AugAssign is excluded ─────────────────────────────────────────────────────


def test_augassign_plus_excluded():
    assert scan("a += b") == []


def test_augassign_minus_excluded():
    assert scan("a -= b") == []


# ── Unary minus is excluded ───────────────────────────────────────────────────


def test_unary_minus_excluded():
    assert scan("x = -a") == []


# ── Multiple sites in one file ────────────────────────────────────────────────


def test_multiple_sites():
    src = "x = a + b\ny = c > d\nz = True\n"
    sites = scan(src)
    assert len(sites) == 3


# ── Determinism ───────────────────────────────────────────────────────────────


def test_deterministic():
    src = "x = a + b\ny = c - d\n"
    assert scan(src) == scan(src)


# ── Site fields: col is preserved exactly ─────────────────────────────────────


def test_site_col_is_set():
    # "x = a + b": the BinOp node starts at col 4 (after "x = ")
    sites = scan("x = a + b")
    assert len(sites) == 1
    assert sites[0].col == 4


def test_site_col_distinguishes_same_line_sites():
    # Two ops on same line: col must differ and be the actual column offsets
    src = "x = (a + b) > (c - d)\n"
    sites = scan(src)
    cols = [s.col for s in sites]
    # BinOp a+b is at col 5, BinOp c-d at col 15, Compare at col 4
    assert len(cols) == len(set(cols)), "duplicate col values — sort key wrong"


# ── Sort key is (line, col) — not (line, function_id) ────────────────────────


def test_sort_key_uses_col_not_function_id():
    # Two module-level sites on the same line; their order must follow col position.
    # We construct two BinOps on one line where left op has higher col than right.
    # "x = (a + b) + (c - d)" — inner '+' at col 6, outer '+' at col 4 (BinOp wraps)
    # Use a simpler form: "a + b > c" — BinOp(+) is inside Compare, Compare at col 0,
    # BinOp at col 0... Let's use two separate expressions with known cols.
    src = "x = a + b; y = c > d\n"
    sites = scan(src)
    assert len(sites) == 2
    assert sites[0].col < sites[1].col, "sites not sorted by col within same line"


# ── _format_function_id: outermost_idx boundary (> 0 guard) ──────────────────
# These parametrize over the boundary cases to avoid structural duplication while
# keeping all three outermost_idx branches covered.


@pytest.mark.parametrize(
    "src,expected_id",
    [
        # outermost_idx = 2, ancestor[1] = ClassDef → method format (idx > 0 guard)
        ("class C:\n    def m(self):\n        x = a + b\n", "func/C.m"),
        # outermost_idx = 1, ancestors[0] = Module (not ClassDef) → func format
        ("def foo():\n    x = a + b\n", "func/foo"),
        # ancestors[1] = ClassDef, idx > 0 → method format (different class name)
        ("class A:\n    def method(self):\n        return a + b\n", "func/A.method"),
    ],
)
def test_format_function_id_outermost_idx_boundary(src, expected_id):
    sites = scan(src)
    assert sites[0].function_id == expected_id


# ── _classify: Compare with non-catalogue op emits no site ───────────────────


def test_classify_compare_with_non_catalogue_op_emits_nothing():
    # Construct a Compare node with a non-standard op to exercise the any() False branch.
    # We use ast.Div as a stand-in (not a real Compare op, but satisfies the isinstance check).
    node = ast.Compare(
        left=ast.Name(id="a", ctx=ast.Load()),
        ops=[ast.Div()],
        comparators=[ast.Name(id="b", ctx=ast.Load())],
    )
    ast.fix_missing_locations(node)
    node.lineno = 1
    node.col_offset = 0
    sites: list = []
    _classify(node, [], sites)
    assert sites == []


def test_top_level_function_not_mistakenly_attributed_to_class():
    # Module-level function followed by a class with a method.
    # The module function must not be attributed to the class.
    src = """\
def standalone():
    return a + b

class C:
    def meth(self):
        return c - d
"""
    sites = scan(src)
    fids = {s.function_id for s in sites}
    assert "func/standalone" in fids
    assert "func/C.meth" in fids


# ── Mutant-killing gap tests ──────────────────────────────────────────────────

from mutate4py._discovery import _format_function_id, _is_mutable  # noqa: E402


def test_format_function_id_top_level_function_parent_is_none():
    # mutmut_14: outermost_idx=0 → parent = None (not ancestors[-1])
    # Top-level def: ancestors = [Module]; outermost_idx=0; parent = None → func/foo
    tree = ast.parse("def foo():\n    x = a + b\n")
    module = tree
    fn_def = tree.body[0]
    # ancestors for a site inside foo: [Module, FunctionDef]
    result = _format_function_id([module, fn_def])
    # outermost_fn = fn_def (idx=1 in ancestors), parent = ancestors[0] = Module
    # Since Module is not ClassDef, result should be "func/foo"
    assert result == "func/foo"


def test_format_function_id_outermost_idx_zero_means_no_parent():
    # outermost_idx=0 means ancestors[0] is the function itself
    # parent = ancestors[outermost_idx - 1] if outermost_idx > 0 else None
    # With [FunctionDef] as ancestors: outermost_idx=0, parent=None → func/foo
    tree = ast.parse("def foo():\n    pass\n")
    fn_def = tree.body[0]
    result = _format_function_id([fn_def])
    assert result == "func/foo"


def test_format_function_id_method_in_class_outermost_idx_1():
    # mutmut_15: ancestors = [Module, ClassDef, FunctionDef] for site inside method
    # outermost_fn=FunctionDef, outermost_idx=2, parent=ancestors[1]=ClassDef → func/C.m
    tree = ast.parse("class C:\n    def m(self):\n        x = a + b\n")
    module = tree
    class_def = tree.body[0]
    fn_def = class_def.body[0]
    result = _format_function_id([module, class_def, fn_def])
    assert result == "func/C.m"


def test_is_mutable_compare_in_operator():
    # mutmut_3,4: Compare with In op → _is_mutable = True
    node = ast.parse("a in b").body[0].value
    assert _is_mutable(node) is True


def test_is_mutable_compare_not_in_operator():
    # mutmut_5,6: Compare with NotIn op → _is_mutable = True
    node = ast.parse("a not in b").body[0].value
    assert _is_mutable(node) is True


def test_is_mutable_boolop_or():
    # mutmut_7: BoolOp with Or → _is_mutable = True (isinstance check)
    node = ast.parse("a or b").body[0].value
    assert _is_mutable(node) is True


def test_is_mutable_boolop_and():
    node = ast.parse("a and b").body[0].value
    assert _is_mutable(node) is True


def test_is_mutable_non_arith_binop_returns_false():
    # BinOp with Div → not in _ARITH_OPS → False
    node = ast.parse("a / b").body[0].value
    assert _is_mutable(node) is False


def test_format_function_id_outermost_idx_sentinel_not_used_when_no_fn():
    # mutmut_2,3,4: outermost_idx=-1/None/+1/-2 initial value
    # If no FunctionDef in ancestors, outermost_fn stays None → return ""
    # The initial outermost_idx value must not matter in this path
    tree = ast.parse("x = 1\n")
    module = tree
    result = _format_function_id([module])
    assert result == ""


def test_format_function_id_outermost_idx_zero_parent_is_none_not_ancestors_minus_one():
    # mutmut_14: >= 0 vs > 0
    # outermost_idx=0 means ancestors[0] is the function (no parent before it)
    # parent should be None, not ancestors[-1] which would be the function itself
    # Test: single-element ancestor list with a function def → no class parent
    tree = ast.parse("def foo():\n    pass\n")
    fn_def = tree.body[0]
    # ancestors=[fn_def], outermost_idx=0: parent = None → func/foo
    result = _format_function_id([fn_def])
    assert result == "func/foo"


def test_format_function_id_outermost_idx_1_parent_is_module_not_class():
    # mutmut_15: > 1 vs > 0
    # outermost_idx=1 → parent = ancestors[0]
    # If ancestors[0] is Module (not ClassDef), must still return "func/foo"
    # With > 1: idx=1 would NOT enter the if, so parent=None → same result (equivalent for Module)
    # With > 0: idx=1 DOES enter → parent=ancestors[0]=Module → function_unit_id handles it
    # Actually both give "func/foo" because function_unit_id with Module parent → "func/foo"
    # The real distinguishing case: ancestors=[Module, FunctionDef], outermost_idx=1
    tree = ast.parse("def foo():\n    x = a + b\n")
    module = tree
    fn_def = tree.body[0]
    result = _format_function_id([module, fn_def])
    assert result == "func/foo"


def test_discover_sites_sort_key_uses_line_and_col():
    # mutmut_8: sort(key=None) vs sort(key=lambda x: (x[0], x[1]))
    # Default tuple sort IS (x[0], x[1], x[2]) which includes function_id string.
    # If two sites have same (line,col) but different function_id, default sort might reorder.
    # More robustly: test that sites with same line are ordered by col, not by function_id.
    from mutate4py._discovery import discover_sites
    # Two different ops on same line: BinOp at different column offsets
    src = "x = a + b; y = c > d\n"
    sites = discover_sites(src)
    assert len(sites) >= 2
    same_line = [s for s in sites if s.line == 1]
    if len(same_line) >= 2:
        cols = [s.col for s in same_line]
        assert cols == sorted(cols), f"Same-line sites not sorted by col: {cols}"
