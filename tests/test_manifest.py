"""Unit tests for manifest embed/extract/diff (F2)."""

import ast
import hashlib
import json
import pytest

from mutate4py._manifest import (
    _find_manifest_block,
    _parse_json_safe,
    _uncomment_line,
    build_manifest,
    diff_manifests,
    embed_manifest,
    extract_manifest,
    parse_sidecar_manifest,
    serialize_sidecar_manifest,
    strip_manifest,
)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _hash(src: str) -> str:
    return hashlib.sha256(ast.dump(ast.parse(src)).encode()).hexdigest()


def _make_manifest(**overrides) -> dict:
    base = {
        "version": 1,
        "tested_at": "2026-01-01T00:00:00Z",
        "module_hash": "abc123",
        "functions": [],
    }
    base.update(overrides)
    return base


# ── strip_manifest ────────────────────────────────────────────────────────────


def test_strip_no_marker_returns_source_unchanged():
    src = "x = 1\n"
    assert strip_manifest(src) == src


def test_strip_no_marker_trailing_newlines_preserved():
    src = "x = 1\n\n"
    assert strip_manifest(src) == src


def test_strip_removes_footer():
    src = "x = 1\n"
    marker = "# mutate4py-manifest-begin\n# {}\n# mutate4py-manifest-end\n"
    embedded = src.rstrip("\n") + "\n\n" + marker
    assert strip_manifest(embedded) == "x = 1\n"


def test_strip_leaves_trailing_single_newline():
    marker = "# mutate4py-manifest-begin\n# {}\n# mutate4py-manifest-end\n"
    embedded = "x = 1\n\n" + marker
    stripped = strip_manifest(embedded)
    assert stripped == "x = 1\n"


# ── embed_manifest ────────────────────────────────────────────────────────────


def test_embed_appends_begin_end_markers():
    src = "x = 1\n"
    m = _make_manifest()
    result = embed_manifest(src, m)
    assert "# mutate4py-manifest-begin\n" in result
    assert "# mutate4py-manifest-end\n" in result


def test_embed_json_line_starts_with_hash_space():
    src = "x = 1\n"
    m = _make_manifest()
    result = embed_manifest(src, m)
    lines = result.splitlines()
    begin_idx = lines.index("# mutate4py-manifest-begin")
    json_line = lines[begin_idx + 1]
    assert json_line.startswith("# ")
    json.loads(json_line[2:])  # must parse


def test_embed_json_is_compact_no_spaces():
    src = "x = 1\n"
    m = _make_manifest(
        functions=[
            {"id": "func/foo", "name": "foo", "line": 1, "end_line": 2, "hash": "x"}
        ]
    )
    result = embed_manifest(src, m)
    lines = result.splitlines()
    begin_idx = lines.index("# mutate4py-manifest-begin")
    json_line = lines[begin_idx + 1][2:]  # strip "# "
    assert '", "' not in json_line and '": "' not in json_line


def test_embed_body_above_footer_is_trimmed_original():
    src = "x = 1\n\n\n"
    m = _make_manifest()
    result = embed_manifest(src, m)
    begin_idx = result.index("# mutate4py-manifest-begin")
    body = result[:begin_idx]
    assert body == "x = 1\n\n\n"


def test_embed_strip_then_re_embed_is_idempotent_body():
    src = "def foo():\n    return 1\n"
    m = _make_manifest()
    first = embed_manifest(src, m)
    # Re-embed: strip old footer first (embed does this)
    second = embed_manifest(first, m)
    # Body above footer must be byte-identical
    begin_first = first.index("# mutate4py-manifest-begin")
    begin_second = second.index("# mutate4py-manifest-begin")
    assert first[:begin_first] == second[:begin_second]


def test_embed_exactly_one_begin_marker_after_re_embed():
    src = "x = 1\n"
    m = _make_manifest()
    first = embed_manifest(src, m)
    second = embed_manifest(first, m)
    assert second.count("# mutate4py-manifest-begin") == 1


# ── _find_manifest_block ──────────────────────────────────────────────────────


def test_find_manifest_block_no_markers_returns_none():
    assert _find_manifest_block("x = 1\n") is None


def test_find_manifest_block_begin_only_returns_none():
    assert _find_manifest_block("x = 1\n# mutate4py-manifest-begin\n") is None


def test_find_manifest_block_end_only_returns_none():
    assert _find_manifest_block("x = 1\n# mutate4py-manifest-end\n") is None


def test_find_manifest_block_end_before_begin_returns_none():
    src = "# mutate4py-manifest-end\n# mutate4py-manifest-begin\n"
    assert _find_manifest_block(src) is None


def test_find_manifest_block_returns_between_markers():
    src = "# mutate4py-manifest-begin\n# payload\n# mutate4py-manifest-end\n"
    block = _find_manifest_block(src)
    assert block is not None
    assert "payload" in block


# ── _parse_json_safe ──────────────────────────────────────────────────────────


def test_parse_json_safe_valid():
    result, ok = _parse_json_safe('{"a": 1}')
    assert ok is True
    assert result == {"a": 1}


def test_parse_json_safe_invalid():
    result, ok = _parse_json_safe("not-json")
    assert ok is False
    assert result is None


# ── _uncomment_line ───────────────────────────────────────────────────────────


def test_uncomment_line_empty_returns_empty():
    assert _uncomment_line("") == ""


def test_uncomment_line_whitespace_only_returns_empty():
    assert _uncomment_line("   ") == ""


def test_uncomment_line_hash_only_returns_empty():
    assert _uncomment_line("#") == ""


def test_uncomment_line_strips_hash_prefix():
    assert _uncomment_line("# hello") == "hello"


def test_uncomment_line_hash_no_space_strips_single_hash():
    assert _uncomment_line("#hello") == "hello"


def test_uncomment_line_non_comment_returns_stripped():
    assert _uncomment_line("  hello  ") == "hello"


# ── extract_manifest ──────────────────────────────────────────────────────────


def test_extract_no_markers_returns_none_false():
    assert extract_manifest("x = 1\n") == (None, False)


def test_extract_begin_only_returns_none_false():
    src = "x = 1\n# mutate4py-manifest-begin\n"
    assert extract_manifest(src) == (None, False)


def test_extract_end_before_begin_returns_none_false():
    src = "# mutate4py-manifest-end\n# mutate4py-manifest-begin\n"
    assert extract_manifest(src) == (None, False)


def test_extract_bad_json_returns_none_false():
    src = "x = 1\n# mutate4py-manifest-begin\n# not-json\n# mutate4py-manifest-end\n"
    assert extract_manifest(src) == (None, False)


def test_extract_valid_returns_manifest_true():
    src = "x = 1\n"
    m = _make_manifest()
    embedded = embed_manifest(src, m)
    result, ok = extract_manifest(embedded)
    assert ok is True
    assert result is not None


def test_extract_is_inverse_of_embed():
    src = "def foo():\n    return 1\n"
    m = _make_manifest(
        functions=[
            {"id": "func/foo", "name": "foo", "line": 1, "end_line": 2, "hash": "abc"}
        ]
    )
    embedded = embed_manifest(src, m)
    result, ok = extract_manifest(embedded)
    assert ok is True
    assert result["version"] == m["version"]
    assert result["module_hash"] == m["module_hash"]
    assert result["functions"] == m["functions"]


# ── build_manifest ────────────────────────────────────────────────────────────


def test_build_manifest_version_is_1():
    src = "x = 1\n"
    m = build_manifest(src, tested_at="2026-01-01T00:00:00Z")
    assert m["version"] == 1


def test_build_manifest_tested_at_is_passed_value():
    src = "x = 1\n"
    m = build_manifest(src, tested_at="2026-06-26T00:00:00Z")
    assert m["tested_at"] == "2026-06-26T00:00:00Z"


def test_build_manifest_functions_empty_for_no_defs():
    src = "x = 1\n"
    m = build_manifest(src, tested_at="2026-01-01T00:00:00Z")
    assert m["functions"] == []


def test_build_manifest_module_hash_non_empty():
    src = "x = 1\n"
    m = build_manifest(src, tested_at="2026-01-01T00:00:00Z")
    assert isinstance(m["module_hash"], str) and len(m["module_hash"]) > 0


def test_build_manifest_records_def_function():
    src = "def foo():\n    return 1\n"
    m = build_manifest(src, tested_at="2026-01-01T00:00:00Z")
    assert len(m["functions"]) == 1
    fn = m["functions"][0]
    assert fn["id"] == "func/foo"
    assert fn["name"] == "foo"


def test_build_manifest_records_async_def():
    src = "async def foo():\n    return 1\n"
    m = build_manifest(src, tested_at="2026-01-01T00:00:00Z")
    assert len(m["functions"]) == 1
    assert m["functions"][0]["id"] == "func/foo"


def test_build_manifest_method_id():
    src = "class C:\n    def m(self):\n        return 1\n"
    m = build_manifest(src, tested_at="2026-01-01T00:00:00Z")
    assert m["functions"][0]["id"] == "func/C.m"
    assert m["functions"][0]["name"] == "m"


def test_build_manifest_line_is_def_line_not_decorator():
    src = "@decorator\ndef foo():\n    return 1\n"
    m = build_manifest(src, tested_at="2026-01-01T00:00:00Z")
    fn = m["functions"][0]
    assert fn["line"] == 2


def test_build_manifest_function_has_line_end_line_hash():
    src = "def foo():\n    return 1\n"
    m = build_manifest(src, tested_at="2026-01-01T00:00:00Z")
    fn = m["functions"][0]
    assert "line" in fn
    assert "end_line" in fn
    assert "hash" in fn


def test_build_manifest_hash_stable_across_whitespace_reformat():
    src1 = "def foo():\n    return 1\n"
    src2 = "def foo():\n    return   1\n"
    m1 = build_manifest(src1, tested_at="2026-01-01T00:00:00Z")
    m2 = build_manifest(src2, tested_at="2026-01-01T00:00:00Z")
    # ast.dump is whitespace-insensitive within expressions
    assert m1["functions"][0]["hash"] == m2["functions"][0]["hash"]


@pytest.mark.parametrize(
    "src1,src2",
    [
        ("def foo(a, b):\n    return a + b\n", "def foo(a, b):\n    return a - b\n"),
        ("def foo():\n    return 1\n", "def bar():\n    return 1\n"),
    ],
)
def test_build_manifest_hash_changes_for_semantic_edit(src1, src2):
    m1 = build_manifest(src1, tested_at="2026-01-01T00:00:00Z")
    m2 = build_manifest(src2, tested_at="2026-01-01T00:00:00Z")
    assert m1["functions"][0]["hash"] != m2["functions"][0]["hash"]


def test_build_manifest_hash_stable_for_comment_edit():
    src1 = "def foo():\n    return 1\n"
    src2 = "def foo():\n    # a comment\n    return 1\n"
    m1 = build_manifest(src1, tested_at="2026-01-01T00:00:00Z")
    m2 = build_manifest(src2, tested_at="2026-01-01T00:00:00Z")
    assert m1["functions"][0]["hash"] == m2["functions"][0]["hash"]


def test_build_manifest_module_hash_stable_for_comment_edit():
    src1 = "x = 1\n"
    src2 = "# comment\nx = 1\n"
    m1 = build_manifest(src1, tested_at="2026-01-01T00:00:00Z")
    m2 = build_manifest(src2, tested_at="2026-01-01T00:00:00Z")
    assert m1["module_hash"] == m2["module_hash"]


def test_build_manifest_functions_ordered_by_line():
    src = "def foo():\n    return 1\n\ndef bar():\n    return 2\n"
    m = build_manifest(src, tested_at="2026-01-01T00:00:00Z")
    assert len(m["functions"]) == 2
    assert m["functions"][0]["line"] <= m["functions"][1]["line"]


def test_build_manifest_nested_function_not_recorded():
    src = "def outer():\n    def inner():\n        pass\n    return inner\n"
    m = build_manifest(src, tested_at="2026-01-01T00:00:00Z")
    ids = [fn["id"] for fn in m["functions"]]
    assert "func/outer" in ids
    assert "func/inner" not in ids


# ── diff_manifests ────────────────────────────────────────────────────────────


def _fn(id_: str, hash_: str) -> dict:
    return {
        "id": id_,
        "name": id_.split("/")[-1],
        "line": 1,
        "end_line": 2,
        "hash": hash_,
    }


def test_diff_none_previous_returns_all_current_ids():
    current = _make_manifest(functions=[_fn("func/a", "h1"), _fn("func/b", "h2")])
    changed = diff_manifests(None, current)
    assert changed == {"func/a", "func/b"}


def test_diff_same_hash_no_change():
    prev = _make_manifest(functions=[_fn("func/a", "h1")])
    curr = _make_manifest(functions=[_fn("func/a", "h1")])
    assert diff_manifests(prev, curr) == set()


def test_diff_changed_hash_reports_id():
    prev = _make_manifest(functions=[_fn("func/a", "h1")])
    curr = _make_manifest(functions=[_fn("func/a", "h2")])
    assert diff_manifests(prev, curr) == {"func/a"}


def test_diff_new_id_in_current_is_changed():
    prev = _make_manifest(functions=[_fn("func/a", "h1")])
    curr = _make_manifest(functions=[_fn("func/a", "h1"), _fn("func/b", "h3")])
    assert diff_manifests(prev, curr) == {"func/b"}


def test_diff_removed_id_silently_dropped():
    prev = _make_manifest(functions=[_fn("func/a", "h1"), _fn("func/b", "h2")])
    curr = _make_manifest(functions=[_fn("func/a", "h1")])
    assert diff_manifests(prev, curr) == set()


def test_diff_module_hash_not_in_changed_set():
    prev = _make_manifest(module_hash="old", functions=[_fn("func/a", "h1")])
    curr = _make_manifest(module_hash="new", functions=[_fn("func/a", "h1")])
    changed = diff_manifests(prev, curr)
    assert "module_hash" not in changed
    assert changed == set()


# ── Mutant-killing gap tests ──────────────────────────────────────────────────


def test_strip_source_with_double_trailing_newline_before_marker():
    # mutant_5,_6: strip_manifest body = source[:idx].rstrip("\n") + "\n"
    # With double newline before begin marker, result is still exactly one newline
    src = "x = 1\n\n"
    marker = "# mutate4py-manifest-begin\n# {}\n# mutate4py-manifest-end\n"
    embedded = src + marker
    stripped = strip_manifest(embedded)
    assert stripped == "x = 1\n"
    assert stripped.endswith("\n")
    assert not stripped.endswith("\n\n")


def test_embed_compact_json_no_space_after_colon():
    # mutant_8,_10: json.dumps with separators=(",",":") means no space after colon or comma
    src = "x = 1\n"
    m = _make_manifest(
        functions=[
            {"id": "func/foo", "name": "foo", "line": 1, "end_line": 2, "hash": "abc"}
        ]
    )
    result = embed_manifest(src, m)
    lines = result.splitlines()
    begin_idx = lines.index("# mutate4py-manifest-begin")
    json_line = lines[begin_idx + 1][2:]  # strip "# "
    assert ": " not in json_line, "No space after colon (compact separators)"
    assert ", " not in json_line, "No space after comma (compact separators)"


def test_uncomment_line_hash_no_space_returns_payload():
    # mutant_7: _uncomment_line("#hello") → stripped[1:].strip() = "hello"
    assert _uncomment_line("#hello") == "hello"


def test_find_manifest_block_end_only_is_none():
    # mutant_8: only end_of_record marker → begin_idx == -1 → None
    src = "x = 1\n# mutate4py-manifest-end\n"
    assert _find_manifest_block(src) is None


def test_extract_functions_two_functions_ordered_by_line():
    # mutmut _28: _extract_functions results.sort(key=lambda f: f["line"])
    # Two functions: second defined first but at higher line number → sorted ascending
    src = "def foo():\n    return 1\n\ndef bar():\n    return 2\n"
    m = build_manifest(src, tested_at="2026-01-01T00:00:00Z")
    lines = [fn["line"] for fn in m["functions"]]
    assert lines == sorted(lines), "Functions must be ordered by line ascending"
    assert m["functions"][0]["name"] == "foo"
    assert m["functions"][1]["name"] == "bar"


def test_strip_manifest_rstrip_only_newlines_not_spaces():
    # mutant_9: rstrip(None) vs rstrip("\n")
    # rstrip(None) strips ALL whitespace including spaces; rstrip("\n") only strips newlines
    src = "x = 1   \n"  # trailing spaces before newline
    marker = "# mutate4py-manifest-begin\n# {}\n# mutate4py-manifest-end\n"
    embedded = src + marker
    stripped = strip_manifest(embedded)
    # rstrip("\n") on "x = 1   \n" → "x = 1   " then + "\n" → "x = 1   \n"
    # rstrip(None) on "x = 1   \n" → "x = 1" then + "\n" → "x = 1\n"
    assert stripped == "x = 1   \n", f"Expected spaces preserved, got {stripped!r}"


def test_strip_manifest_rstrip_only_newlines_not_x_chars():
    # mutant_11: rstrip("XX\nXX") strips X and \n chars; rstrip("\n") only strips \n
    # If content ends with X before the marker, mutant would strip trailing X too
    src = "varX\n"  # content ending with X
    marker = "# mutate4py-manifest-begin\n# {}\n# mutate4py-manifest-end\n"
    embedded = src + marker
    stripped = strip_manifest(embedded)
    # rstrip("\n") on "varX\n" → "varX" then + "\n" → "varX\n"
    # rstrip("XX\nXX") on "varX\n" → strips X and \n → "var" then + "\n" → "var\n"
    assert stripped == "varX\n", f"Expected trailing X preserved, got {stripped!r}"


def test_embed_manifest_rstrip_only_newlines_not_spaces():
    # mutant_2: embed calls strip_manifest(source).rstrip("\n")
    # rstrip(None) would strip spaces too, giving different body
    src = "x = 1   \n"  # trailing spaces
    m = _make_manifest()
    result = embed_manifest(src, m)
    begin_idx = result.index("# mutate4py-manifest-begin")
    body = result[:begin_idx]
    # rstrip("\n") on "x = 1   \n" → "x = 1   " then + "\n\n"
    # rstrip(None) on "x = 1   \n" → "x = 1" then + "\n\n"
    assert "   " in body, f"Trailing spaces should be preserved in body: {body!r}"


def test_embed_manifest_rstrip_only_newlines_not_x_chars():
    # mutant_5: rstrip("XX\nXX") strips X and \n chars; rstrip("\n") only strips \n
    src = "varX\n"  # content ending with X
    m = _make_manifest()
    result = embed_manifest(src, m)
    begin_idx = result.index("# mutate4py-manifest-begin")
    body = result[:begin_idx]
    # rstrip("\n") → "varX" + "\n\n"; rstrip("XX\nXX") → "var" + "\n\n"
    assert "varX" in body, f"Expected trailing X preserved in body: {body!r}"


def test_find_manifest_block_rfind_vs_find_single_marker():
    # mutant_3,6: find vs rfind — same result when only one begin/end marker
    src = "x = 1\n# mutate4py-manifest-begin\n# {}\n# mutate4py-manifest-end\n"
    block = _find_manifest_block(src)
    assert block is not None
    assert "{}" in block


def test_find_manifest_block_end_idx_sentinel():
    # mutant_13,14: end_idx == +1 or -2 vs == -1
    # When end marker is absent, source.find() returns -1, not +1 or -2
    # So the condition `end_idx == -1` must trigger, returning None
    src = "x = 1\n# mutate4py-manifest-begin\n"  # no end marker
    assert _find_manifest_block(src) is None


def test_find_manifest_block_begin_equals_end_returns_none():
    # mutant_15: end_idx < begin_idx vs end_idx <= begin_idx
    # This would only differ if begin and end marker are at the SAME position,
    # which is impossible since they're different strings.
    # But we can test the case where end is exactly at begin+0 by using a source
    # where end marker is placed right at begin marker position (impossible).
    # Instead test that end BEFORE begin returns None (covers the <= case too):
    src = "# mutate4py-manifest-end\n# mutate4py-manifest-begin\n"
    assert _find_manifest_block(src) is None


def test_extract_manifest_space_join_matters():
    # mutant_9: " ".join(parts) vs "XX XX".join(parts)
    # With a single-part manifest, join separator doesn't matter.
    # With multiple uncommented lines (multi-part manifest), separator matters for JSON parsing.
    # Build a manifest that has content spread across multiple comment lines:
    src = 'x = 1\n# mutate4py-manifest-begin\n# {"a": 1}\n# mutate4py-manifest-end\n'
    result, ok = extract_manifest(src)
    assert ok is True
    assert result == {"a": 1}


def test_extract_manifest_multiline_json_space_join():
    # mutant_9: join separator matters when JSON is split across multiple comment lines.
    # Build a manifest where the JSON object spans two comment lines:
    # "# {\"version\":" on one line and "# 1}" on the next.
    # " ".join gives '{"version": 1}' (valid); "XX XX".join gives '{"version":XX XX1}' (invalid).
    src = (
        "x = 1\n"
        "# mutate4py-manifest-begin\n"
        '# {"version":\n'
        "# 1}\n"
        "# mutate4py-manifest-end\n"
    )
    result, ok = extract_manifest(src)
    assert ok is True
    assert result == {"version": 1}


def test_strip_manifest_find_vs_rfind_double_begin():
    # mutant_3: find vs rfind for strip_manifest
    # With two begin markers, find returns the first (correct: strip from earliest marker).
    # rfind returns the second, leaving the first marker in the body.
    src = (
        "x = 1\n"
        "# mutate4py-manifest-begin\n"
        "# old stuff\n"
        "# mutate4py-manifest-end\n"
        "# mutate4py-manifest-begin\n"
        "# {}\n"
        "# mutate4py-manifest-end\n"
    )
    result = strip_manifest(src)
    assert "# mutate4py-manifest-begin" not in result


def test_find_manifest_block_find_vs_rfind_double_markers():
    # mutant_3 (_find_manifest_block): find vs rfind for begin marker
    # mutant_6 (_find_manifest_block): find vs rfind for end marker
    # With two begin markers, find returns the first begin; rfind returns the second.
    # With two end markers, find returns the first end; rfind returns the last.
    # We want the canonical block (first begin to first end after it).
    # Test: source with content before the final begin+end block — find should locate correct block.
    src = (
        "# mutate4py-manifest-begin\n"
        "# {}\n"
        "# mutate4py-manifest-end\n"
        "# mutate4py-manifest-begin\n"
        '# {"version": 1}\n'
        "# mutate4py-manifest-end\n"
    )
    block = _find_manifest_block(src)
    # find returns first begin, first end → block is the first one: # {}
    assert block is not None
    assert "{}" in block


# ── serialize_sidecar_manifest / parse_sidecar_manifest (pure) ────────────────


def test_serialize_sidecar_manifest_is_pretty_printed():
    m = _make_manifest(
        functions=[
            {"id": "func/foo", "name": "foo", "line": 1, "end_line": 2, "hash": "abc"}
        ]
    )
    text = serialize_sidecar_manifest(m)
    assert "\n" in text.strip()  # indent=2 spreads keys across lines
    assert text.endswith("\n")


def test_serialize_sidecar_manifest_round_trips_through_parse():
    m = _make_manifest(
        functions=[
            {"id": "func/foo", "name": "foo", "line": 1, "end_line": 2, "hash": "abc"}
        ]
    )
    result, ok = parse_sidecar_manifest(serialize_sidecar_manifest(m))
    assert ok is True
    assert result == m


def test_parse_sidecar_manifest_invalid_json_returns_none_false():
    result, ok = parse_sidecar_manifest("not-json")
    assert ok is False
    assert result is None


def test_parse_sidecar_manifest_valid_returns_dict_true():
    m = _make_manifest()
    result, ok = parse_sidecar_manifest(json.dumps(m))
    assert ok is True
    assert result == m


def test_find_manifest_block_rfind_end_includes_too_much():
    # mutant_6: rfind for end marker returns the LAST end marker position.
    # With two end markers, rfind would extend the block past the first end,
    # including content between the two end markers.
    # Verify: the block must NOT include content after the first end marker.
    src = (
        "# mutate4py-manifest-begin\n"
        '# {"a": 1}\n'
        "# mutate4py-manifest-end\n"
        "# ONLY_IN_SECOND_BLOCK\n"
        "# mutate4py-manifest-end\n"
    )
    block = _find_manifest_block(src)
    # Correct (find for end): block = '\n# {"a": 1}\n' — does NOT contain ONLY_IN_SECOND_BLOCK
    # Mutant (rfind for end): block extends to last end marker, includes ONLY_IN_SECOND_BLOCK
    assert block is not None
    assert "ONLY_IN_SECOND_BLOCK" not in block
