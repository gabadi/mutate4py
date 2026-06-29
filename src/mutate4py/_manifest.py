"""Manifest embed, extract, diff, and build — faithful port of mutate4go's manifest.go."""

import ast
import hashlib
import json
import re

from mutate4py._ids import function_unit_id

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

    Format (port of mutate4go Strip/Embed):
      <body, trailing newlines trimmed> + "\n\n"
      + "# mutate4py-manifest-begin\n# " + <single-line JSON> + "\n"
      + "# mutate4py-manifest-end\n"
    """
    clean = strip_manifest(source).rstrip("\n")
    json_line = json.dumps(manifest, separators=(",", ":"))
    return clean + "\n\n" + _BEGIN + "\n" + "# " + json_line + "\n" + _END + "\n"


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


def _parse_json_safe(text: str) -> tuple[dict | None, bool]:
    try:
        return json.loads(text), True
    except (json.JSONDecodeError, ValueError):
        return None, False


def extract_manifest(source: str) -> tuple[dict | None, bool]:
    """Extract the manifest from source.

    Returns (manifest_dict, True) on success, (None, False) on missing markers
    or parse failure.
    """
    block = _find_manifest_block(source)
    if block is None:
        return None, False
    parts = [p for line in block.splitlines() if (p := _uncomment_line(line))]
    return _parse_json_safe(" ".join(parts))


def _sha256_ast(node: ast.AST) -> str:
    return hashlib.sha256(ast.dump(node).encode()).hexdigest()


def manifests_structurally_equal(a: dict, b: dict) -> bool:
    """Return True if a and b have the same module_hash and function id→hash mapping.

    Ignores tested_at.
    """
    if a.get("module_hash") != b.get("module_hash"):
        return False
    a_fns = {fn["id"]: fn["hash"] for fn in a.get("functions", [])}
    b_fns = {fn["id"]: fn["hash"] for fn in b.get("functions", [])}
    return a_fns == b_fns


def build_manifest(source: str, *, tested_at: str) -> dict:
    """Build a manifest for source.

    source should be manifest-stripped before calling this.
    Hash = sha256(ast.dump(node)) with default args (position-independent).
    module_hash = sha256(ast.dump(module_tree)).
    """
    tree = ast.parse(source)
    module_hash = _sha256_ast(tree)
    functions = _extract_functions(tree)

    return {
        "version": 1,
        "tested_at": tested_at,
        "module_hash": module_hash,
        "functions": functions,
    }


def _extract_functions(tree: ast.Module) -> list[dict]:
    """Extract outermost named function units with their id, name, line, end_line, hash."""
    results = []
    # Iterative walk tracking parent to detect outermost functions
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
            # children are inside a function now
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


# mutate4py-manifest-begin
# {"version":1,"tested_at":"2026-06-29T00:53:58Z","module_hash":"b498d06b6bb6b9cd83e58b693098957f92b00ee4cd6fac008503b32224cb30bb","functions":[{"id":"func/strip_manifest","name":"strip_manifest","line":16,"end_line":26,"hash":"483f574c872014cbd0a648d46ede8053b7e184ceca5312619931d0581d7fa5ad"},{"id":"func/embed_manifest","name":"embed_manifest","line":29,"end_line":39,"hash":"2dbe501eafe93559def91df32229dd290b56924fd33bfdce8436cc993579ae47"},{"id":"func/_uncomment_line","name":"_uncomment_line","line":42,"end_line":49,"hash":"77aa349f4739873120c4793b0acc65ff13a0c64dc20e89f7459d6b603a7edff1"},{"id":"func/_find_manifest_block","name":"_find_manifest_block","line":52,"end_line":58,"hash":"c1c350ba64ba2dac198501764857a556c4c9f4739fcb750cd9c21f254121ea18"},{"id":"func/_parse_json_safe","name":"_parse_json_safe","line":61,"end_line":65,"hash":"62144fde8b4ace85518ad659062c82ea487dc9093aabae72faabc68962dc0eec"},{"id":"func/extract_manifest","name":"extract_manifest","line":68,"end_line":78,"hash":"6d3a9573a70b76d4786bf878bde3692b6eaa5651041ce36249b4902aa0cd86cb"},{"id":"func/_sha256_ast","name":"_sha256_ast","line":81,"end_line":82,"hash":"e829902fac5e57696acf2366ccc1a8b6334c3ae72fa570e1b4cdd5bd02d6ac64"},{"id":"func/manifests_structurally_equal","name":"manifests_structurally_equal","line":85,"end_line":94,"hash":"8f0255ddb865869926016105721885d429a5bdf6b09a74b175e43a0583b9d809"},{"id":"func/build_manifest","name":"build_manifest","line":97,"end_line":113,"hash":"f3f8a17425017eca331265c741e25916260d97c50bd8b155c871a99e83404731"},{"id":"func/_extract_functions","name":"_extract_functions","line":116,"end_line":145,"hash":"c3191d0dc37595306d1111e24b4bf2354bd57e035383d62641ad3ad6aebbe073"},{"id":"func/diff_manifests","name":"diff_manifests","line":148,"end_line":165,"hash":"60a7610fd215fa99b62d169a7c92435cc228057382a55ca013fe44a802e177a6"}]}
# mutate4py-manifest-end
