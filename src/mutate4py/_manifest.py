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


def serialize_sidecar_manifest(manifest: dict) -> str:
    """Render a manifest as sidecar-file JSON text: pretty-printed with a trailing newline."""
    return json.dumps(manifest, indent=2) + "\n"


def parse_sidecar_manifest(text: str) -> tuple[dict | None, bool]:
    """Parse sidecar-file JSON text into a manifest. Parse failure => (None, False)."""
    return _parse_json_safe(text)


def _sha256_ast(node: ast.AST) -> str:
    return hashlib.sha256(ast.unparse(node).encode()).hexdigest()


def manifests_structurally_equal(a: dict, b: dict) -> bool:
    """Return True if a and b have the same module_hash and function id→hash mapping.

    Ignores tested_at.
    """
    if a.get("module_hash") != b.get("module_hash"):
        return False
    a_fns = {fn["id"]: fn["hash"] for fn in a.get("functions", [])}
    b_fns = {fn["id"]: fn["hash"] for fn in b.get("functions", [])}
    return a_fns == b_fns


def reconcile_manifest(existing: dict | None, candidate: dict) -> dict:
    """Return the manifest to embed: existing (preserving its tested_at) if
    structurally equal to candidate, otherwise candidate itself."""
    if existing is not None and manifests_structurally_equal(existing, candidate):
        return existing
    return candidate


def build_manifest(source: str, *, tested_at: str) -> dict:
    """Build a manifest for source.

    source should be manifest-stripped before calling this.
    Hash = sha256(ast.unparse(node)) — canonical source, version-stable.
    module_hash = sha256(ast.unparse(module_tree)).
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
# PLACEHOLDER - regenerated below via `mutate4py --update-manifest`
# mutate4py-manifest-end
