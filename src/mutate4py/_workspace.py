"""uv workspace autodiscovery (issue #22 items 3, 8-12).

Zero positional arguments trigger this: climb from cwd to the nearest
ancestor `pyproject.toml`, require it to declare `[tool.uv.workspace]`, then
resolve `members`/`exclude` globs against that workspace root (not cwd).
Mirrors uv's own `find_workspace` — stdlib `tomllib` only, never a `uv`
subprocess. Requires Python 3.11+ (tomllib is stdlib there); the project's
`requires-python` floor was bumped to match rather than adding a `tomli`
dependency.
"""

import glob
import os
import sys
import tomllib
from collections.abc import Sequence


def _find_pyproject(start: str) -> str | None:
    """Climb from start (inclusive) to the nearest ancestor's pyproject.toml.

    Returns None if none is found up to the filesystem root.
    """
    current = os.path.abspath(start)
    while True:
        candidate = os.path.join(current, "pyproject.toml")
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _exit_no_pyproject_found(cwd: str) -> None:
    print(
        f"error: no [tool.uv.workspace] found; searched from {cwd} upward, "
        "no pyproject.toml. Pass a path explicitly.",
        file=sys.stderr,
    )
    sys.exit(2)


def _exit_no_workspace_table(pyproject_path: str) -> None:
    print(f"error: {pyproject_path} has no [tool.uv.workspace].", file=sys.stderr)
    sys.exit(2)


def _load_toml(path: str) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _workspace_table(data: dict) -> dict | None:
    return data.get("tool", {}).get("uv", {}).get("workspace")


def _load_workspace_config() -> tuple[str, dict]:
    """Return (workspace_root, workspace_table); exits 2 on any failure."""
    cwd = os.getcwd()
    pyproject_path = _find_pyproject(cwd)
    if pyproject_path is None:
        _exit_no_pyproject_found(cwd)
    data = _load_toml(pyproject_path)
    workspace = _workspace_table(data)
    if workspace is None:
        _exit_no_workspace_table(pyproject_path)
    return os.path.dirname(pyproject_path), workspace


def _resolve_dirs(workspace_root: str, patterns: Sequence[str]) -> list[str]:
    """Directories matched by patterns, resolved against workspace_root."""
    dirs: list[str] = []
    for pattern in patterns:
        full_pattern = os.path.join(workspace_root, pattern)
        matches = sorted(glob.glob(full_pattern, recursive=True))
        dirs.extend(m for m in matches if os.path.isdir(m))
    return dirs


def _resolve_member_dirs(workspace_root: str, patterns: Sequence[str]) -> list[str]:
    """Member dirs (item 9): glob-matched directories with their own
    pyproject.toml; a match without one is skipped silently."""
    dirs = _resolve_dirs(workspace_root, patterns)
    return [d for d in dirs if os.path.isfile(os.path.join(d, "pyproject.toml"))]


def _is_excluded_dir(d: str, excluded: Sequence[str]) -> bool:
    """True if d equals, or sits under, any excluded directory."""
    return any(d == ex or d.startswith(ex + os.sep) for ex in excluded)


def _discover_workspace_roots() -> list[str]:
    """Roots for the zero-positional path: the workspace root, then every
    member directory (items 3, 8-11), root order preserved (item 15)."""
    workspace_root, workspace = _load_workspace_config()
    excluded = _resolve_dirs(workspace_root, workspace.get("exclude", []))
    members = _resolve_member_dirs(workspace_root, workspace.get("members", []))
    kept_members = [d for d in members if not _is_excluded_dir(d, excluded)]
    return [workspace_root] + kept_members


def _workspace_exclude_dirs() -> list[str]:
    """Directories to prune from the workspace root's recursive walk
    (item 10's second half); re-parses the same workspace config."""
    workspace_root, workspace = _load_workspace_config()
    return _resolve_dirs(workspace_root, workspace.get("exclude", []))


# mutate4py-manifest-begin
# {"version":1,"tested_at":"2026-08-05T16:01:34Z","module_hash":"4ac506cba27c8746efb8e5c616584db1f358f222b324b259d41d826f64cdf6a3","functions":[{"id":"func/_find_pyproject","name":"_find_pyproject","line":19,"end_line":32,"hash":"04f3e0c7f7a6fc4c348645147119e2748936ff5e3890eeffe6fb8c0d80fb3f8b"},{"id":"func/_exit_no_pyproject_found","name":"_exit_no_pyproject_found","line":35,"end_line":41,"hash":"e88f818abbaf483dafc18d261403fc1d8807f859e902d09460f1bd58d5e9cdd8"},{"id":"func/_exit_no_workspace_table","name":"_exit_no_workspace_table","line":44,"end_line":46,"hash":"66c99eec46a339bd96794020dd8af222aa3a711df6cfe6745166e5c5aef5a0e6"},{"id":"func/_load_toml","name":"_load_toml","line":49,"end_line":51,"hash":"32809ec1bfb21913821a400cb62624931cd9bc62cd9f010951b80e6c93599f2d"},{"id":"func/_workspace_table","name":"_workspace_table","line":54,"end_line":55,"hash":"a07f248b77917e030e08ff97548fe8a18f5bb7e58663165988de979f5fcc8a13"},{"id":"func/_load_workspace_config","name":"_load_workspace_config","line":58,"end_line":68,"hash":"f4d5f4e9366f4333a34aa9e4aa17b662b6960b297b237be154433df5e4375cf2"},{"id":"func/_resolve_dirs","name":"_resolve_dirs","line":71,"end_line":78,"hash":"a6dbbc238f2b2949d680ac1ffbfaee2f285934f7c94c317987f329b2d51dfbf8"},{"id":"func/_resolve_member_dirs","name":"_resolve_member_dirs","line":81,"end_line":85,"hash":"dcc817758fdadd1ee1aada7a9b40028adb5af03f35bf172e131bb4948e6a1942"},{"id":"func/_is_excluded_dir","name":"_is_excluded_dir","line":88,"end_line":90,"hash":"cbfad646d44179d595f92fe2661938f71c33569dbd9e61b25fff1eb95b5f7398"},{"id":"func/_discover_workspace_roots","name":"_discover_workspace_roots","line":93,"end_line":100,"hash":"da8aa9dfabef27d094e5b46eede19fc15f218eb5eb88c51ea5b83fbeb8d39bbf"},{"id":"func/_workspace_exclude_dirs","name":"_workspace_exclude_dirs","line":103,"end_line":107,"hash":"d438febc6ad461ccd70e39c76e8d16b6a9633a1580b9e9e083a5a510b4d8843b"}]}
# mutate4py-manifest-end
