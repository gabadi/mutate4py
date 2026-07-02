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
# {"version":1,"tested_at":"2026-07-02T02:00:12Z","module_hash":"a096c70657f69e47fb895e8ef9408947eb2e5f3671f339fe9519f9181a997b65","functions":[{"id":"func/strip_manifest","name":"strip_manifest","line":16,"end_line":26,"hash":"0c3dad79fa2576414fcfa48ad47748f2e0d76663a010c4b1ff0d931c04228808"},{"id":"func/embed_manifest","name":"embed_manifest","line":29,"end_line":41,"hash":"d8484437c75b1f787827b5feafdd640555357e86cc462aa7778f7beafd3c559d"},{"id":"func/_uncomment_line","name":"_uncomment_line","line":44,"end_line":51,"hash":"78c51423cd2362a1afa89007a26546d6c00ecfd5fd9f38f85502e50b7e29881f"},{"id":"func/_find_manifest_block","name":"_find_manifest_block","line":54,"end_line":60,"hash":"df04720e974840c1630bbe4444419dbcbb431505d103384f205eeb8d06cc2b4d"},{"id":"func/_parse_json_safe","name":"_parse_json_safe","line":63,"end_line":67,"hash":"16004732bb738b9003e78bfe43a7ee8238b61439e7a89532eb24befdb8979744"},{"id":"func/extract_manifest","name":"extract_manifest","line":70,"end_line":80,"hash":"2b17c77f37ccaac7b6af38c7670e112d598bc49a1fae4dc773b1e83a3c3cb833"},{"id":"func/_sha256_ast","name":"_sha256_ast","line":83,"end_line":84,"hash":"45da0f51e024b5fe64b95084f3074f927412338fc1d1e1d2f1690b0c4a66b3c5"},{"id":"func/manifests_structurally_equal","name":"manifests_structurally_equal","line":87,"end_line":96,"hash":"9ef437e0385515525621e5149161a4068f1a736be66a44063aab492aa79c35f3"},{"id":"func/build_manifest","name":"build_manifest","line":99,"end_line":115,"hash":"a735b486e2c5d362e01a5565c3f03b93132012a8fda9355eb6ef4670081c4781"},{"id":"func/_extract_functions","name":"_extract_functions","line":118,"end_line":147,"hash":"3de7d42663139b5f954dc01f0fd172f4d3429d72803a46ddc9ef6939e265d9eb"},{"id":"func/diff_manifests","name":"diff_manifests","line":150,"end_line":167,"hash":"7dace38d003dfc04471fbace27a7ab228e09f8aeb32129ae570598ba2b40eeb5"}]}
# mutate4py-manifest-end
