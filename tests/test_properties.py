"""Property tests for manifest round-trips, ID-format invariants, partition_sites, discovery, and worker assignment."""

import ast

from hypothesis import given, settings
from hypothesis import strategies as st

from mutate4py._discovery import Site, apply_mutant, discover_sites, partition_sites
from mutate4py._manifest import (
    build_manifest,
    diff_manifests,
    embed_manifest,
    extract_manifest,
    manifests_structurally_equal,
    strip_manifest,
)


# ── strip / embed round-trip ──────────────────────────────────────────────────

_BODY = st.text(
    alphabet=st.characters(blacklist_characters="\x00"),
    min_size=0,
    max_size=200,
).filter(lambda s: "mutate4py-manifest-begin" not in s)

_MANIFEST = st.fixed_dictionaries(
    {
        "version": st.just(1),
        "tested_at": st.just("2026-01-01T00:00:00Z"),
        "module_hash": st.text(min_size=1, max_size=64),
        "functions": st.just([]),
    }
)


@given(body=_BODY, manifest=_MANIFEST)
def test_extract_is_inverse_of_embed(body, manifest):
    embedded = embed_manifest(body, manifest)
    recovered, ok = extract_manifest(embedded)
    assert ok
    assert recovered["version"] == manifest["version"]
    assert recovered["module_hash"] == manifest["module_hash"]


@given(body=_BODY, manifest=_MANIFEST)
def test_strip_after_embed_recovers_normalised_body(body, manifest):
    embedded = embed_manifest(body, manifest)
    stripped = strip_manifest(embedded)
    # stripped ends with exactly one newline
    assert stripped.endswith("\n")
    assert not stripped.endswith("\n\n")


@given(body=_BODY, manifest=_MANIFEST)
def test_embed_idempotent_body_section(body, manifest):
    first = embed_manifest(body, manifest)
    second = embed_manifest(first, manifest)
    begin1 = first.index("# mutate4py-manifest-begin")
    begin2 = second.index("# mutate4py-manifest-begin")
    assert first[:begin1] == second[:begin2]


@given(body=_BODY, manifest=_MANIFEST)
def test_embed_exactly_one_begin_marker(body, manifest):
    result = embed_manifest(body, manifest)
    assert result.count("# mutate4py-manifest-begin") == 1


# ── manifests_structurally_equal ──────────────────────────────────────────────

_FN_ENTRY = st.fixed_dictionaries(
    {
        "id": st.from_regex(r"func/[a-zA-Z_]\w*", fullmatch=True),
        "hash": st.text(min_size=8, max_size=64),
    }
)

_MANIFEST_WITH_FNS = st.fixed_dictionaries(
    {
        "version": st.just(1),
        "tested_at": st.just("2026-01-01T00:00:00Z"),
        "module_hash": st.text(min_size=1, max_size=64),
        "functions": st.lists(_FN_ENTRY, min_size=0, max_size=5, unique_by=lambda f: f["id"]),
    }
)


@given(m=_MANIFEST_WITH_FNS)
def test_manifest_equal_to_itself(m):
    assert manifests_structurally_equal(m, m)


@given(m=_MANIFEST_WITH_FNS, tested_at=st.text(min_size=1, max_size=30))
def test_manifest_equal_ignores_tested_at(m, tested_at):
    import copy

    m2 = copy.deepcopy(m)
    m2["tested_at"] = tested_at
    assert manifests_structurally_equal(m, m2)


# ── diff_manifests ────────────────────────────────────────────────────────────


@given(m=_MANIFEST_WITH_FNS)
def test_diff_none_previous_returns_all_ids(m):
    changed = diff_manifests(None, m)
    expected = {fn["id"] for fn in m["functions"]}
    assert changed == expected


@given(m=_MANIFEST_WITH_FNS)
def test_diff_same_manifest_no_changes(m):
    import copy

    assert diff_manifests(m, copy.deepcopy(m)) == set()


@given(m=_MANIFEST_WITH_FNS)
def test_diff_result_subset_of_current_ids(m):
    import copy

    changed = diff_manifests(copy.deepcopy(m), m)
    current_ids = {fn["id"] for fn in m["functions"]}
    assert changed <= current_ids


# ── build_manifest + strip ────────────────────────────────────────────────────

_SIMPLE_PY = st.sampled_from(
    [
        "x = 1\n",
        "def foo():\n    return 1\n",
        "def foo(a, b):\n    return a + b\n",
        "class C:\n    def m(self):\n        pass\n",
        "pass\n",
    ]
)


@given(src=_SIMPLE_PY)
def test_build_then_embed_then_extract_roundtrip(src):
    m = build_manifest(src, tested_at="2026-01-01T00:00:00Z")
    embedded = embed_manifest(src, m)
    recovered, ok = extract_manifest(embedded)
    assert ok
    assert recovered["module_hash"] == m["module_hash"]
    assert recovered["functions"] == m["functions"]


@given(src=_SIMPLE_PY)
def test_build_manifest_version_always_1(src):
    m = build_manifest(src, tested_at="2026-01-01T00:00:00Z")
    assert m["version"] == 1


@given(src=_SIMPLE_PY)
def test_build_manifest_module_hash_stable(src):
    m1 = build_manifest(src, tested_at="2026-01-01T00:00:00Z")
    m2 = build_manifest(src, tested_at="2099-12-31T00:00:00Z")
    assert m1["module_hash"] == m2["module_hash"]
    assert m1["functions"] == m2["functions"]


# ── partition_sites ───────────────────────────────────────────────────────────

_SITE_LINES = st.lists(st.integers(min_value=1, max_value=100), min_size=0, max_size=30)
_COVERED_LINES = st.frozensets(st.integers(min_value=1, max_value=100))


def _sites_from_lines(lines: list[int]) -> list[Site]:
    return [
        Site(
            index=i,
            line=ln,
            col=0,
            end_line=ln,
            end_col=1,
            function_id="",
            orig_text="x",
            mutant_text="y",
            desc="x -> y",
        )
        for i, ln in enumerate(lines)
    ]


@given(lines=_SITE_LINES, covered=_COVERED_LINES)
def test_partition_sites_count_conserved(lines, covered):
    sites = _sites_from_lines(lines)
    c, u = partition_sites(sites, set(covered))
    assert c + u == len(sites)


@given(lines=_SITE_LINES, covered=_COVERED_LINES)
def test_partition_sites_covered_non_negative(lines, covered):
    sites = _sites_from_lines(lines)
    c, u = partition_sites(sites, set(covered))
    assert c >= 0 and u >= 0


@given(lines=_SITE_LINES)
def test_partition_sites_empty_covered_all_uncovered(lines):
    sites = _sites_from_lines(lines)
    c, u = partition_sites(sites, set())
    assert c == 0 and u == len(sites)


@given(lines=_SITE_LINES)
def test_partition_sites_full_covered_all_covered(lines):
    sites = _sites_from_lines(lines)
    all_lines = {s.line for s in sites}
    c, u = partition_sites(sites, all_lines)
    assert c == len(sites) and u == 0


# ── discover_sites + apply_mutant invariants ──────────────────────────────────


def _is_valid_python(source: str) -> bool:
    try:
        ast.parse(source)
        return True
    except SyntaxError:
        return False


_PYTHON_SOURCES = st.sampled_from(
    [
        "def f(a, b):\n    return a > b\n",
        "def f(a, b):\n    return a >= b\n",
        "def f(a, b):\n    return a < b\n",
        "def f(a, b):\n    return a <= b\n",
        "def f(a, b):\n    return a == b\n",
        "def f(a, b):\n    return a != b\n",
        "def f(a, b):\n    return a + b\n",
        "def f(a, b):\n    return a - b\n",
        "def f(a, b):\n    return a * b\n",
        "def f(a, b):\n    return a > b and True\n",
        "def f(a, b):\n    return a > b or False\n",
        "def f(a, b):\n    if a > b:\n        return 1\n    return 0\n",
        "x = 0\n",
        "x = 1\n",
        "x = True\n",
        "x = False\n",
    ]
)


@given(_PYTHON_SOURCES)
@settings(max_examples=60)
def test_apply_mutant_always_differs_from_clean(source: str) -> None:
    """Every mutant produced by apply_mutant must differ from the clean source."""
    sites = discover_sites(source)
    for site in sites:
        mutated = apply_mutant(source, site)
        assert mutated != source, (
            f"apply_mutant produced identical source for site index={site.index} line={site.line} desc={site.desc!r}"
        )


@given(_PYTHON_SOURCES)
@settings(max_examples=60)
def test_apply_mutant_contains_mutant_text(source: str) -> None:
    """The mutated source must contain the site's mutant_text."""
    sites = discover_sites(source)
    for site in sites:
        mutated = apply_mutant(source, site)
        assert site.mutant_text in mutated, (
            f"mutant_text {site.mutant_text!r} not found after applying site {site.index}"
        )


@given(_PYTHON_SOURCES)
@settings(max_examples=60)
def test_discover_sites_indices_are_unique_and_zero_based(source: str) -> None:
    """Site indices must be unique and form a 0-based contiguous range."""
    sites = discover_sites(source)
    indices = [s.index for s in sites]
    assert indices == list(range(len(sites))), f"Non-contiguous or duplicate indices: {indices}"


@given(_PYTHON_SOURCES)
@settings(max_examples=60)
def test_discover_sites_sorted_by_line_col(source: str) -> None:
    """Sites must be sorted by (line, col)."""
    sites = discover_sites(source)
    pairs = [(s.line, s.col) for s in sites]
    assert pairs == sorted(pairs), f"Sites not sorted: {pairs}"


# ── _assign_sites_to_workers invariants ───────────────────────────────────────


def _make_indexed_site(index: int) -> Site:
    return Site(
        index=index,
        line=index + 1,
        col=0,
        end_line=index + 1,
        end_col=5,
        function_id="func/f",
        orig_text=">",
        mutant_text=">=",
        desc="> -> >=",
    )


@given(
    n_sites=st.integers(min_value=1, max_value=50),
    n_workers=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=80)
def test_assign_sites_every_site_appears_exactly_once(n_sites: int, n_workers: int) -> None:
    """Every site must appear in exactly one worker's assignment list."""
    from mutate4py._workers import _assign_sites_to_workers

    sites = [_make_indexed_site(i) for i in range(n_sites)]
    by_worker = _assign_sites_to_workers(sites, n_workers)

    assigned_indices: list[int] = []
    for assignments in by_worker.values():
        for _worker_idx, site, _site_idx in assignments:
            assigned_indices.append(site.index)

    assert sorted(assigned_indices) == list(range(n_sites))


@given(
    n_sites=st.integers(min_value=1, max_value=50),
    n_workers=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=80)
def test_assign_sites_worker_keys_in_bounds(n_sites: int, n_workers: int) -> None:
    """All worker keys must be in range [1, n_workers]."""
    from mutate4py._workers import _assign_sites_to_workers

    sites = [_make_indexed_site(i) for i in range(n_sites)]
    by_worker = _assign_sites_to_workers(sites, n_workers)
    for worker_key in by_worker.keys():
        assert 1 <= worker_key <= n_workers


@given(
    n_sites=st.integers(min_value=1, max_value=50),
    n_workers=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=80)
def test_assign_sites_site_idx_is_1_based_global_position(n_sites: int, n_workers: int) -> None:
    """site_idx in each assignment must equal site.index + 1 (1-based global position)."""
    from mutate4py._workers import _assign_sites_to_workers

    sites = [_make_indexed_site(i) for i in range(n_sites)]
    by_worker = _assign_sites_to_workers(sites, n_workers)

    for assignments in by_worker.values():
        for _worker_idx, site, site_idx in assignments:
            assert site_idx == site.index + 1, (
                f"site.index={site.index} but site_idx={site_idx} (expected {site.index + 1})"
            )
