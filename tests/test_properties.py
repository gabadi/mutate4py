"""Property tests for manifest round-trips and ID-format invariants."""

from hypothesis import given
from hypothesis import strategies as st

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

_MANIFEST = st.fixed_dictionaries({
    "version": st.just(1),
    "tested_at": st.just("2026-01-01T00:00:00Z"),
    "module_hash": st.text(min_size=1, max_size=64),
    "functions": st.just([]),
})


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

_FN_ENTRY = st.fixed_dictionaries({
    "id": st.from_regex(r"func/[a-zA-Z_]\w*", fullmatch=True),
    "hash": st.text(min_size=8, max_size=64),
})

_MANIFEST_WITH_FNS = st.fixed_dictionaries({
    "version": st.just(1),
    "tested_at": st.just("2026-01-01T00:00:00Z"),
    "module_hash": st.text(min_size=1, max_size=64),
    "functions": st.lists(_FN_ENTRY, min_size=0, max_size=5, unique_by=lambda f: f["id"]),
})


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

_SIMPLE_PY = st.sampled_from([
    "x = 1\n",
    "def foo():\n    return 1\n",
    "def foo(a, b):\n    return a + b\n",
    "class C:\n    def m(self):\n        pass\n",
    "pass\n",
])


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
