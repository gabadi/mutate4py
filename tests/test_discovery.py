"""Unit tests for mutation site discovery (F1 — site-discovery)."""

import textwrap
import pytest
from mutate4py._discovery import discover_sites


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


def test_top_level_def():
    src = "def foo():\n    x = a + b\n"
    sites = scan(src)
    assert len(sites) == 1
    assert sites[0].function_id == "func/foo"


def test_async_def():
    src = "async def foo():\n    x = a + b\n"
    sites = scan(src)
    assert sites[0].function_id == "func/foo"


def test_method_in_class():
    src = "class C:\n    def m(self):\n        x = a + b\n"
    sites = scan(src)
    assert sites[0].function_id == "func/C.m"


def test_module_level_no_def():
    src = "x = a + b\n"
    sites = scan(src)
    assert sites[0].function_id == ""


def test_nested_def_folds_into_outer():
    src = """\
        def outer():
            def inner():
                x = a + b
    """
    sites = scan(src)
    assert all(s.function_id == "func/outer" for s in sites)


def test_lambda_folds_into_enclosing():
    src = """\
        def outer():
            f = lambda: a + b
    """
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
