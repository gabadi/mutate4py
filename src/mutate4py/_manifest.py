"""Manifest embed, extract, diff, and build — faithful port of mutate4go's manifest.go."""

import ast
import hashlib
import json
import re
from collections import Counter

from mutate4py._ids import function_unit_id
from mutate4py._sidecar_io import parse_json_text

_BEGIN = "# mutate4py-manifest-begin"
_END = "# mutate4py-manifest-end"
_BEGIN_RE = re.compile(r"^" + re.escape(_BEGIN) + r"$", re.MULTILINE)
_END_RE = re.compile(r"^" + re.escape(_END) + r"$", re.MULTILINE)


def strip_manifest(source: str) -> str:
    """Remove the manifest footer from source, returning the clean body.

    If no begin marker is found, returns source unchanged.
    Result always ends with exactly one newline (trailing-newline trim, then add one).
    """
    m = _BEGIN_RE.search(source)
    if m is None:
        return source
    body = source[: m.start()].rstrip("\n") + "\n"
    return body


def embed_manifest(source: str, manifest: dict) -> str:
    """Embed manifest into source, replacing any existing footer.

    Format (ruff-format-compatible: two blank lines before a trailing
    top-level comment block, none if the body is empty):
      <body, trailing newlines trimmed> + "\n\n\n" (omitted if body is empty)
      + "# mutate4py-manifest-begin\n# " + <single-line JSON> + "\n"
      + "# mutate4py-manifest-end\n"
    """
    clean = strip_manifest(source).rstrip("\n")
    json_line = json.dumps(manifest, separators=(",", ":"))
    separator = "\n\n\n" if clean else ""
    return clean + separator + _BEGIN + "\n" + "# " + json_line + "\n" + _END + "\n"


def _uncomment_line(line: str) -> str:
    """Strip leading whitespace and a single `#` prefix; return the payload or ''."""
    stripped = line.strip()
    if not stripped:
        return ""
    if stripped.startswith("#"):
        stripped = stripped[1:].strip()
    return stripped


def _find_manifest_block(source: str) -> str | None:
    """Return the text between the begin and end markers, or None if not found."""
    begin_m = _BEGIN_RE.search(source)
    end_m = _END_RE.search(source)
    if begin_m is None or end_m is None or end_m.start() <= begin_m.start():
        return None
    return source[begin_m.end() : end_m.start()]


def extract_manifest(source: str) -> tuple[dict | None, bool]:
    """Extract the manifest from source.

    Returns (manifest_dict, True) on success, (None, False) on missing markers
    or parse failure.
    """
    block = _find_manifest_block(source)
    if block is None:
        return None, False
    parts = [p for line in block.splitlines() if (p := _uncomment_line(line))]
    return parse_json_text(" ".join(parts))


def _sha256_ast(node: ast.AST) -> str:
    return hashlib.sha256(ast.unparse(node).encode()).hexdigest()


def source_sha256(source: str) -> str:
    """SHA-256 of manifest-stripped source bytes — the level-1 fast-path fingerprint.

    Byte-level, not AST-level: a comment-only edit changes this value even though
    it leaves every Unit hash unchanged. One-way only — a match proves nothing
    changed; a mismatch proves nothing about what changed, it just means the real
    parse (level 2) must run.
    """
    return hashlib.sha256(source.encode()).hexdigest()


def manifests_structurally_equal(a: dict, b: dict) -> bool:
    """Return True if a and b have the same module_hash and function id→hash mapping.

    Ignores tested_at.
    """
    if a.get("module_hash") != b.get("module_hash"):
        return False
    a_fns = {fn["id"]: fn["hash"] for fn in a.get("functions", [])}
    b_fns = {fn["id"]: fn["hash"] for fn in b.get("functions", [])}
    return a_fns == b_fns


_UNIT_KEYS = ("id", "name", "line", "end_line", "hash")


def _scored_fields(fn: dict) -> dict | None:
    """The canonical score block of a function entry, or None when it is unscored.

    Missing values read as defaults: a missing score int is 0, a missing or
    null list is [], a missing desc or reason is "", a missing line is 0. A list
    entry that is not a dict is skipped.
    """
    score = fn.get("score")
    if not isinstance(score, dict):
        return None
    return {
        "score": {
            "killed": score.get("killed", 0),
            "survived": score.get("survived", 0),
            "uncovered": score.get("uncovered", 0),
        },
        "survivors": [
            {"line": s.get("line", 0), "desc": s.get("desc", "")}
            for s in _list_field(fn, "survivors")
            if isinstance(s, dict)
        ],
        "accepted": [
            {"line": a.get("line", 0), "desc": a.get("desc", ""), "reason": a.get("reason", "")}
            for a in _list_field(fn, "accepted")
            if isinstance(a, dict)
        ],
    }


def _list_field(fn: dict, key: str) -> list:
    """A list field of a function entry; a missing or null list reads as []."""
    return fn.get(key) or []


def _fields_for(fn: dict, prev: dict | None, scores: dict[str, dict] | None) -> dict | None:
    """Score fields for one candidate function: rescored this run, else kept
    while its hash is unchanged, else None (changed or new, so unscored)."""
    if scores is not None and fn["id"] in scores:
        return _scored_fields(scores[fn["id"]])
    if prev is not None and prev.get("hash") == fn["hash"]:
        return _scored_fields(prev)
    return None


def _scored_by_id(manifest: dict | None) -> dict[str, dict | None]:
    if manifest is None:
        return {}
    return {fn["id"]: _scored_fields(fn) for fn in manifest["functions"]}


def reconcile_manifest(existing: dict | None, candidate: dict, scores: dict[str, dict] | None = None) -> dict:
    """Return the manifest to embed, carrying each function's score block forward.

    A function rescored this run takes its fields from scores. An unchanged
    function (same hash as in existing) keeps its fields. A changed or new
    function has none, so it stays unscored until a scored run records it.

    Returns existing itself when nothing but tested_at or source_sha256 would
    change (ADR 0006), so callers detect "unchanged" by identity.
    """
    prior = {fn["id"]: fn for fn in existing["functions"]} if existing is not None else {}
    entries = [_carry_entry(fn, prior.get(fn["id"]), scores) for fn in candidate["functions"]]
    merged = {**candidate, "functions": entries}
    if _unchanged(existing, merged):
        return existing
    return merged


def _carry_entry(fn: dict, prev: dict | None, scores: dict[str, dict] | None) -> dict:
    """Unit keys plus the score fields this function keeps or gains this run."""
    entry = {k: fn[k] for k in _UNIT_KEYS}
    entry.update(_fields_for(fn, prev, scores) or {})
    return entry


def _unchanged(existing: dict | None, merged: dict) -> bool:
    """True when merged differs from existing only in tested_at or source_sha256, scores included (ADR 0006)."""
    return (
        existing is not None
        and manifests_structurally_equal(existing, merged)
        and _scored_by_id(existing) == _scored_by_id(merged)
    )


def functions_with_survivors(manifest: dict | None) -> set[str]:
    """Ids of functions with recorded survivors: they are not current. None gives an empty set."""
    if manifest is None:
        return set()
    return {fn["id"] for fn in manifest["functions"] if (_scored_fields(fn) or {}).get("survivors")}


def functions_with_unmarked_acceptances(manifest: dict | None, current: dict, markers: dict[int, str]) -> set[str]:
    """Ids of functions whose accepted survivor lost its marker.

    That covers a marker removed, its reason reworded, or one of several
    same-reason markers removed. markers maps line -> reason for the current
    source. A marker counts for a function when it sits inside that function's
    current span, so a function whose code merely moved keeps its acceptance.
    None gives an empty set.
    """
    if manifest is None:
        return set()
    current_by_id = {fn["id"]: fn for fn in current["functions"]}
    return {
        fn["id"]
        for fn in manifest["functions"]
        if fn["id"] in current_by_id and _acceptance_unmarked(fn, current_by_id[fn["id"]], markers)
    }


def _acceptance_unmarked(fn: dict, cur: dict, markers: dict[int, str]) -> bool:
    """True when cur's span holds fewer markers of some accepted reason than fn's accepted survivors need.

    A marker accepts every survivor on its line, so each distinct (line, reason)
    needs one marker of that reason. Two same-reason survivors on two lines need
    two markers, so removing one of them is caught.
    """
    accepted = (_scored_fields(fn) or {}).get("accepted")
    if not accepted:
        return False
    found = _markers_in_span(cur, markers)
    needed = Counter(reason for _, reason in {(a["line"], a["reason"]) for a in accepted})
    return any(count > found[reason] for reason, count in needed.items())


def _markers_in_span(cur: dict, markers: dict[int, str]) -> Counter[str]:
    """Per reason, the markers that sit inside cur's line span."""
    return Counter(reason for line, reason in markers.items() if cur["line"] <= line <= cur["end_line"])


def has_accepted_survivors(manifest: dict) -> bool:
    """True when any function records an accepted survivor, whose marker check needs the parse."""
    return any((_scored_fields(fn) or {}).get("accepted") for fn in manifest["functions"])


def recorded_survivors(manifest: dict) -> list[tuple[str, dict]]:
    """Every recorded survivor as (function id, {"line", "desc"}), in manifest function order."""
    return [(fn["id"], s) for fn in manifest["functions"] for s in (_scored_fields(fn) or {}).get("survivors", [])]


def is_unscored(manifest: dict) -> bool:
    """True when any function lacks a score block. A manifest with no functions is not unscored."""
    return any(_scored_fields(fn) is None for fn in manifest["functions"])


def build_manifest(source: str, *, tested_at: str) -> dict:
    """Build a manifest for source.

    source should be manifest-stripped before calling this.
    Hash = sha256(ast.unparse(node)) — canonical source, version-stable.
    module_hash = sha256(ast.unparse(module_tree)).
    source_sha256 = sha256(source) — byte-level fingerprint for check_manifest's
    fast path; not part of manifests_structurally_equal.
    """
    tree = ast.parse(source)
    module_hash = _sha256_ast(tree)
    functions = _extract_functions(tree)

    return {
        "version": 1,
        "tested_at": tested_at,
        "module_hash": module_hash,
        "source_sha256": source_sha256(source),
        "functions": functions,
    }


def _extract_functions(tree: ast.Module) -> list[dict]:
    """Extract outermost named function units with their id, name, line, end_line, hash."""
    results = []
    stack: list[tuple[ast.AST, ast.AST | None, bool]] = [(tree, None, False)]
    while stack:
        node, parent, inside_fn = stack.pop()

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not inside_fn:
                fid = function_unit_id(node, parent)
                results.append(
                    {
                        "id": fid,
                        "name": node.name,
                        "line": node.lineno,
                        "end_line": node.end_lineno,
                        "hash": _sha256_ast(node),
                    }
                )
            for child in ast.iter_child_nodes(node):
                stack.append((child, node, True))
        else:
            for child in ast.iter_child_nodes(node):
                stack.append((child, node, inside_fn))

    # Sort by line for determinism
    results.sort(key=lambda f: f["line"])
    return results


def diff_manifests(previous: dict | None, current: dict) -> set[str]:
    """Return the set of changed function ids.

    previous is None => every current id is changed.
    A current id is changed iff its hash differs from previous (or is new).
    Removed ids (in previous, not current) are silently dropped.
    module_hash is NOT part of the diff set.
    """
    if previous is None:
        return {fn["id"] for fn in current["functions"]}

    prev_hashes = {fn["id"]: fn["hash"] for fn in previous["functions"]}
    changed = set()
    for fn in current["functions"]:
        prev_hash = prev_hashes.get(fn["id"])
        if prev_hash != fn["hash"]:
            changed.add(fn["id"])
    return changed
