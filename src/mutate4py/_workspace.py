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
        f"error: no [tool.uv.workspace] found; searched from {cwd} upward, no pyproject.toml. Pass a path explicitly.",
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
