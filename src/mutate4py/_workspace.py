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


def _exit_bad_pyproject(path: str, reason: str) -> None:
    print(f"error: could not read {path}: {reason}", file=sys.stderr)
    sys.exit(2)


def _exit_bad_workspace_key(pyproject_path: str, key: str) -> None:
    print(
        f"error: {pyproject_path} [tool.uv.workspace].{key} must be a list of strings.",
        file=sys.stderr,
    )
    sys.exit(2)


def _load_toml(path: str) -> dict:
    """Parse path as TOML; exits 2 naming it on any read/parse failure
    (malformed TOML, permission denied, etc. — never an uncaught crash)."""
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        _exit_bad_pyproject(path, str(exc))


def _workspace_table(data: dict) -> dict | None:
    return data.get("tool", {}).get("uv", {}).get("workspace")


def _workspace_list(workspace_root: str, workspace: dict, key: str) -> list[str]:
    """The validated list[str] at workspace[key] (default []); exits 2
    naming the file if it's present but not a list of strings — including
    a bare string, which Python would otherwise iterate character-by-
    character."""
    value = workspace.get(key, [])
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return value
    pyproject_path = os.path.join(workspace_root, "pyproject.toml")
    _exit_bad_workspace_key(pyproject_path, key)


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
    """Directories matched by patterns, resolved against workspace_root,
    ".."-normalized, and deduped by realpath (a `**` pattern crossing a
    symlink cycle can otherwise rediscover the same directory many times)."""
    dirs: list[str] = []
    seen_real: set[str] = set()
    for pattern in patterns:
        full_pattern = os.path.normpath(os.path.join(workspace_root, pattern))
        for m in sorted(glob.glob(full_pattern, recursive=True)):
            if not os.path.isdir(m):
                continue
            real = os.path.realpath(m)
            if real in seen_real:
                continue
            seen_real.add(real)
            dirs.append(m)
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
    exclude_patterns = _workspace_list(workspace_root, workspace, "exclude")
    member_patterns = _workspace_list(workspace_root, workspace, "members")
    excluded = _resolve_dirs(workspace_root, exclude_patterns)
    members = _resolve_member_dirs(workspace_root, member_patterns)
    kept_members = [d for d in members if not _is_excluded_dir(d, excluded)]
    return [workspace_root] + kept_members


def _workspace_exclude_dirs() -> list[str]:
    """Directories to prune from the workspace root's recursive walk
    (item 10's second half); re-parses the same workspace config."""
    workspace_root, workspace = _load_workspace_config()
    exclude_patterns = _workspace_list(workspace_root, workspace, "exclude")
    return _resolve_dirs(workspace_root, exclude_patterns)


# mutate4py-manifest-begin
# {"version":1,"tested_at":"2026-08-05T16:18:19Z","module_hash":"0f3109f8371fee438330a2fd8901c5d7ed26f1b1d447ed9a87f437a228172310","functions":[{"id":"func/_find_pyproject","name":"_find_pyproject","line":19,"end_line":32,"hash":"04f3e0c7f7a6fc4c348645147119e2748936ff5e3890eeffe6fb8c0d80fb3f8b"},{"id":"func/_exit_no_pyproject_found","name":"_exit_no_pyproject_found","line":35,"end_line":41,"hash":"e88f818abbaf483dafc18d261403fc1d8807f859e902d09460f1bd58d5e9cdd8"},{"id":"func/_exit_no_workspace_table","name":"_exit_no_workspace_table","line":44,"end_line":46,"hash":"66c99eec46a339bd96794020dd8af222aa3a711df6cfe6745166e5c5aef5a0e6"},{"id":"func/_exit_bad_pyproject","name":"_exit_bad_pyproject","line":49,"end_line":51,"hash":"d28968ebf3fd11eee22cb2dce59f0351123231802ded9d2716408fb5170508a7"},{"id":"func/_exit_bad_workspace_key","name":"_exit_bad_workspace_key","line":54,"end_line":59,"hash":"436a4d0da69fde436b55654172ff298234713580c67fa2c1cce098d9b2af721e"},{"id":"func/_load_toml","name":"_load_toml","line":62,"end_line":69,"hash":"87b867c769f6c70acf7b86b6698aea318d56a7400003212c162c27b2afbac052"},{"id":"func/_workspace_table","name":"_workspace_table","line":72,"end_line":73,"hash":"a07f248b77917e030e08ff97548fe8a18f5bb7e58663165988de979f5fcc8a13"},{"id":"func/_workspace_list","name":"_workspace_list","line":76,"end_line":85,"hash":"366d6bd55f6289a6385d2dbfda067de52b9a02d775bf0eb0e07bc77d9c18fc51"},{"id":"func/_load_workspace_config","name":"_load_workspace_config","line":88,"end_line":98,"hash":"f4d5f4e9366f4333a34aa9e4aa17b662b6960b297b237be154433df5e4375cf2"},{"id":"func/_resolve_dirs","name":"_resolve_dirs","line":101,"end_line":117,"hash":"1d40075ff14b99c39b7692f7a81973c630aa5ccede25957ce306e3a2d55b61ab"},{"id":"func/_resolve_member_dirs","name":"_resolve_member_dirs","line":120,"end_line":124,"hash":"dcc817758fdadd1ee1aada7a9b40028adb5af03f35bf172e131bb4948e6a1942"},{"id":"func/_is_excluded_dir","name":"_is_excluded_dir","line":127,"end_line":129,"hash":"cbfad646d44179d595f92fe2661938f71c33569dbd9e61b25fff1eb95b5f7398"},{"id":"func/_discover_workspace_roots","name":"_discover_workspace_roots","line":132,"end_line":141,"hash":"d7e0d0ee32d6e98f11ec3905d8aacac147c53d3badc97b6d57778769b21b2541"},{"id":"func/_workspace_exclude_dirs","name":"_workspace_exclude_dirs","line":144,"end_line":149,"hash":"7eee43120ced8fe816d25e4647683eaf8ddd87fdf3ce4fffc76eda2fbfd68504"}]}
# mutate4py-manifest-end
