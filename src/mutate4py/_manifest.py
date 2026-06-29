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
# {"version":1,"tested_at":"2026-06-29T00:38:23Z","module_hash":"ef57988278693ec3abe1a483f4bc06240f9d011a54b52e39f0677d3a0118af25","functions":[{"id":"func/strip_manifest","name":"strip_manifest","line":16,"end_line":26,"hash":"57cc48ac32031cbf22882f68601bbafeb0ba24cd34be9b09b26fc44d5ac6e8a2"},{"id":"func/embed_manifest","name":"embed_manifest","line":29,"end_line":39,"hash":"06a96e3c1b56d4d9d6f16a99a09416af9808d72f9dc5f6867e2a7090dbd4f251"},{"id":"func/_uncomment_line","name":"_uncomment_line","line":42,"end_line":49,"hash":"352a3390bba6d399eaa38c45a3d94d66f4c20962b17f664f900cbee15ab28a3b"},{"id":"func/_find_manifest_block","name":"_find_manifest_block","line":52,"end_line":58,"hash":"9bfd03fd74d08dce10dd2ece9ffe564cd89128821ba46d41aa2262a026d48097"},{"id":"func/_parse_json_safe","name":"_parse_json_safe","line":61,"end_line":65,"hash":"669c6c746fbfaa4dfc1a8f18da4da20ed40a0c6e2598742aad9ae4d77d08afed"},{"id":"func/extract_manifest","name":"extract_manifest","line":68,"end_line":78,"hash":"6f3a5413e7f5eac5198f501a2a8550919c8f026606001b06683ab85da1fc9156"},{"id":"func/_sha256_ast","name":"_sha256_ast","line":81,"end_line":82,"hash":"d09da87dc661be0c9a9748c86b471b20d644e4318fdb6072fb7297991f30857f"},{"id":"func/manifests_structurally_equal","name":"manifests_structurally_equal","line":85,"end_line":94,"hash":"d4dee9da7d7eff52d51e3dfbe3f458db40e86bfc34750782b649d4e0094c850d"},{"id":"func/build_manifest","name":"build_manifest","line":97,"end_line":113,"hash":"5103c0f1581db3ac1b181e1ca72f93a21ef1b9c0e3c70c047c30f93d3b2be8f3"},{"id":"func/_extract_functions","name":"_extract_functions","line":116,"end_line":145,"hash":"77c03efc48f2f04ca8e37a7962864ba330f8ec0a6088df12288ae9da5e0cb883"},{"id":"func/diff_manifests","name":"diff_manifests","line":148,"end_line":165,"hash":"556049e031cbd409e9fc90193f45022f0994e0de7d152aa9f21f93f09acae770"}]}
# mutate4py-manifest-end
