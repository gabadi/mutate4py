"""Pinned-digest corpus guarding manifest hash stability across CPython versions.

`build_manifest` hashes `ast.unparse` output, and `ast.unparse` is not a frozen
contract between CPython minors. When two machines run different minors and
`ast.unparse` renders a construct differently, they disagree on that unit's hash
— so `--check-manifest` fails on one and passes on the other for byte-identical
source. `test_manifest.py` compares hashes *relatively* (same hash before and
after a reformat, which holds on any single interpreter); these pin the
*absolute* digest, so drift shows up as a failure naming the exact construct.

Every fixture is a module containing exactly one function, so `ast.unparse` of
the module and of the function node produce the same text and therefore the same
digest — one pinned value covers both `module_hash` and the function hash.

Every digest below was produced by running `build_manifest`, none by hand.
"""

import sys

import pytest

from mutate4py._manifest import build_manifest

_TESTED_AT = "2026-01-01T00:00:00Z"


def _hashes(src: str) -> tuple[str, str]:
    """Return (module_hash, hash of the single outermost function) for src."""
    manifest = build_manifest(src, tested_at=_TESTED_AT)
    (fn,) = manifest["functions"]
    return manifest["module_hash"], fn["hash"]


# ── Version-stable corpus ─────────────────────────────────────────────────────
#
# Constructs whose `ast.unparse` rendering is identical on CPython 3.11 through
# 3.15, verified by running this corpus under all five. name -> (source, digest).

STABLE_CORPUS: dict[str, tuple[str, str]] = {
    "annotations_and_defaults": (
        "def f(a: int = 1, /, b: 'str' = '', *c: int, d: list[int] | None = None, **e: object) -> dict[str, int]:\n    return {}\n",
        "8b00617672b9704d538e82525a244132f7b0879c1ff83fd94a0e52088a771ad0",
    ),
    "attribute_and_subscript_chain": (
        "def f(a):\n    return a.b.c(1).d[2].e\n",
        "cf8c98006e22d71a3bdd2e4885ef8782f786fb2eba28fb1e534a9f3b492b3d2d",
    ),
    "await_precedence": (
        "async def f(a):\n    return (await a).attr + await a\n",
        "aa7757e574905bc8a2733a21c7353e24ebdef0c856aef1660647f405da344f03",
    ),
    "boolop_precedence": (
        "def f(a, b, c):\n    return (a or b) and c or not (a and b)\n",
        "65b3b752ee9e548fd3e55a912892f3158631c701a69933e8a117666559efaddf",
    ),
    "bytes_and_escapes": (
        "def f():\n    return (b'\\x00\\n', '\\t\\u00e9', r'raw\\d+')\n",
        "132a78aef8130b5328b668c819117a6c162c4f9a9f4eb2d5118230a718152436",
    ),
    "chained_compare": (
        "def f(a, b, c):\n    return a < b <= c != a is not b not in c\n",
        "055a8c6234d13baa3a1e8ef15ddf26b43a6cb7071ad6606aa426b2acd2c90c6e",
    ),
    "class_with_bases_kwargs": (
        "def f():\n    class C(Base, metaclass=M, **kw):\n        x: int = 1\n    return C\n",
        "230fa711581855c9e7e442b6a9821f22dfbde8d008c554cb8b994ccac127eb25",
    ),
    "conditional_expr_in_call": (
        "def f(a, b):\n    return g(a if b else b, key=a if a else b)\n",
        "ca644c4c87cb957f3ae557be5d3144b025381f593b5c5dd62b48bd25a657f7f1",
    ),
    "conditional_expr_nested": (
        "def f(a, b, c):\n    return (a if b else c) if c else (b if a else c)\n",
        "d6b967e7369a2570a3ae8890f27dbc5bef7cd07734da927dba76a8ac067b140a",
    ),
    "decorator_complex_expr": (
        "def outer():\n    @reg[0].deco(x=1)\n    def inner():\n        pass\n    return inner\n",
        "c97ce3ded0f79eff11a3e4731accea4a7427a6a97fc8a9b83bf4eb2d61f1a6c9",
    ),
    "docstring_quotes": (
        'def f():\n    """Doc with \'single\' and "double" quotes."""\n    return 1\n',
        "645121d083a426346fc3d9e12f64dc7aa081da723b86d08630f4bcda8e7b61bb",
    ),
    "empty_containers_and_tuple": (
        "def f():\n    return ((), (1,), [], {}, set(), {1})\n",
        "8cedc4cdf44043c1a94d7204cb5f3d661d4cc0fdb111a4333aca07e33cbf4b8d",
    ),
    "fstring_braces_literal": (
        'def f(x):\n    return f"{{{x}}}"\n',
        "bca6b2681da78853ae57d4d400e73de72b3c7f8ef9ac2d73cb3ff67dc9881f15",
    ),
    "fstring_conversion": (
        'def f(x):\n    return f"{x!r} {x!s} {x!a}"\n',
        "700e9bcbb6fbabe9ada2beaafbbe24fa601a4b2de1ad0087b86b5ee3abc93554",
    ),
    "fstring_debug_eq": (
        'def f(x):\n    return f"{x=}"\n',
        "af072796d0f34203840df9cd43ff729e295ae930536999e4b42a6e058b53c650",
    ),
    "fstring_expression": (
        'def f(a, b):\n    return f"{a + b}"\n',
        "ba273f8ce6ebc9e869cfb0dbaccd2b7c1460756b95495e9bd87a6e7cc49e53e2",
    ),
    "fstring_format_spec": (
        'def f(x, w):\n    return f"{x:>{w}.2f}"\n',
        "5bba05199935ac8f227e43d667fe67d1cad0281376c22028da04c6f20030d632",
    ),
    "fstring_simple": (
        'def f(x):\n    return f"v={x}"\n',
        "f811830f578d9d4d63ba5dd35d3f7a5f96a7be50a0ae60f0218f0a6466d24d8b",
    ),
    "genexp_nested_clauses": (
        "def f(m):\n    return sum(y for x in m for y in x if y)\n",
        "17334644fc120ed8079fc0e5eb9d436b37d0074b927c39322c4d2712b095b87f",
    ),
    "genexp_sole_arg": (
        "def f(xs):\n    return sum(x * 2 for x in xs)\n",
        "9c2bcf412597176e4764b5399afb88e12eb7674b6209eec8932cc0260686f19c",
    ),
    "genexp_with_other_args": (
        "def f(xs):\n    return max((x for x in xs), default=0)\n",
        "9080f777d2c7a71cb58c64c6ee640d5548d3c1de0211f5362c66db73d7975622",
    ),
    "global_del_assert": (
        "def f():\n    global G\n    del G\n    assert G, 'msg'\n",
        "11a644d8df68de4802a6fe1dd55ab6ce3daac53fc7ad89a8a832a8c3bdc7f321",
    ),
    "implicit_string_concat": (
        "def f():\n    return 'a' 'b' 'c'\n",
        "098ed2217418c8735b2fbcbc6703be875705b623da999ec4d6e2aebe8aed1fd2",
    ),
    "lambda_default_and_call": (
        "def f():\n    return (lambda x=1, *a, k=2, **kw: x + k)(3)\n",
        "d541ef0c35ef2a18f0e6cfb2c36d0e1622b4de34e2a1ea2d9c8713a85e30df18",
    ),
    "match_as_capture": (
        "def f(x):\n    match x:\n        case [1, 2] as pair:\n            return pair\n        case str() | bytes() as s:\n            return s\n",
        "e1443a1a5030866a9302bc31731daf7b204b3ec359ae3b24a7099a03b266963d",
    ),
    "match_class_sequence_mapping": (
        "def f(p):\n    match p:\n        case Point(x=0, y=0) | Point(x=1):\n            return 'origin'\n        case [a, *rest] if a > 0:\n            return rest\n        case {'k': v, **extra}:\n            return (v, extra)\n",
        "ae02b58b38befc261aca5854d6383e15792684647450fb18244a4448e74b24c5",
    ),
    "match_literal": (
        "def f(x):\n    match x:\n        case 1:\n            return 'one'\n        case _:\n            return 'other'\n",
        "96cb753bfd80e5db388d415e81578cbd93e5a78e0028eb2a18814e217c680be0",
    ),
    "nested_comprehension_conditions": (
        "def f(m):\n    return {k: [v for v in vs if v] for k, vs in m.items() if vs}\n",
        "0e690af7d44ba84727e75298a16cf302eb84b519911a280ac51602bdd745f89a",
    ),
    "numeric_literals": (
        "def f():\n    return (1_000, 0x_FF, 1e10, 1j, 0o17, 0b1010)\n",
        "e2accf2a539526d7240acc63c5a8218356ce8aa109748d496b6b2a0788096725",
    ),
    "slice_complex": (
        "def f(a):\n    return a[1:2:3, ..., ::-1, :]\n",
        "205f563bd3fbc2db2c9e4438b62d4b1463de7fb87ec1cf846e84aa057efd05cc",
    ),
    "starred_unpacking": (
        "def f(a, b):\n    return ([*a, *b], {**a, **b}, g(*a, **b))\n",
        "a26fdfa945988c09a20c6e4117e6de46d2d0f2da9324e79a40e006cda2f50ef7",
    ),
    "try_star_groups": (
        "def f():\n    try:\n        g()\n    except* ValueError as e:\n        return e\n    finally:\n        h()\n",
        "b92044dfbb500683bebec90a0d2d4cbeeba51d296819a13fcdbb912e668df6f6",
    ),
    "unary_power_precedence": (
        "def f(a):\n    return -(a**2) + (-a) ** 2\n",
        "6a6374cc149ab71e725a60a7b0667c07f673e6cbb06b0ccc23dc5a0ecce591a4",
    ),
    "walrus_in_comprehension": (
        "def f(xs):\n    return [y for x in xs if (y := x * 2) > 4]\n",
        "4cbd52c7ea4751a3415200ecb25a5bd4df9dd5dda5ed9d25ffeacd8e36dee83d",
    ),
    "walrus_in_if": (
        "def f(x):\n    if (n := len(x)) > 3:\n        return n\n    return 0\n",
        "dab21d3e5298c233fd3bcb9d5b1beb179c30664aa3ec450a68cb4a9000dd643a",
    ),
    "walrus_in_while": (
        "def f(it):\n    while chunk := it.read():\n        yield chunk\n",
        "8022220566c07dc4463b0dce241a3eb250755d4ac3366c2bf43fcd1247563808",
    ),
    "with_multiple_items": (
        "def f():\n    with open('a') as a, open('b') as b:\n        return (a, b)\n",
        "aac6e25c64184f6564d4a7da38ebaf6ec816ae688a6771431b0a39d6ff9eea06",
    ),
    "yield_in_expression": (
        "def f(a):\n    x = yield a\n    y = yield from a\n    return (x, y)\n",
        "b6a5d8c3fd0f1ea9832912db44bdace83f4b460fc4149279d056a9859785b1d5",
    ),
}


@pytest.mark.parametrize("name", sorted(STABLE_CORPUS))
def test_stable_corpus_digest_is_pinned(name):
    src, expected = STABLE_CORPUS[name]
    assert _hashes(src) == (expected, expected)


# ── Known cross-version divergence ────────────────────────────────────────────
#
# PEP 701 let f-strings reuse the enclosing quote character inside replacement
# fields. On 3.12 and 3.13 `ast.unparse` emits that form — f'{d['k']}' — while
# 3.11 predates it and 3.14 reverted to escaping — f"{d['k']}" — so 3.11/3.14/3.15
# agree with each other and disagree with 3.12/3.13. Any function containing such
# an f-string hashes differently depending on the interpreter. That is a real
# defect in the hash's version-stability, pinned here rather than papered over, so
# the split stays visible and a *third* rendering fails loudly.

_QUOTE_REUSE_MINORS = {(3, 12), (3, 13)}

QUOTE_REUSE_CORPUS: dict[str, tuple[str, str, str]] = {
    "fstring_nested_fstring": (
        "def f(x):\n    return f\"{f'{x}'}\"\n",
        "90f1c2b933491b8f7fee64a6618f10cbeb18775ccc3c4ea55f6ccca6a2962a28",
        "b6de157982ca362db563b4bb55f52a07f0696323ae6f236fdbb922a70ac1ba1b",
    ),
    "fstring_nested_quotes": (
        "def f(d):\n    return f\"{d['k']}\"\n",
        "39f5ac49a8bcc2edfb6ed6cbc193a4eacf3fcf3269b0f2306c4b41f9aa9eac8a",
        "89938dfe96d586718c447bf2731c22de1772b9d1b3cd448e60cf3808d17ca963",
    ),
}


@pytest.mark.parametrize("name", sorted(QUOTE_REUSE_CORPUS))
def test_quote_reuse_corpus_digest_is_pinned_per_minor(name):
    src, reuse_digest, escaped_digest = QUOTE_REUSE_CORPUS[name]
    expected = (
        reuse_digest if sys.version_info[:2] in _QUOTE_REUSE_MINORS else escaped_digest
    )
    assert _hashes(src) == (expected, expected)


@pytest.mark.parametrize("name", sorted(QUOTE_REUSE_CORPUS))
def test_quote_reuse_corpus_genuinely_diverges(name):
    _, reuse_digest, escaped_digest = QUOTE_REUSE_CORPUS[name]
    assert reuse_digest != escaped_digest
