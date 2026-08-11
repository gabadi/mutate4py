"""Turns positional arguments into a concrete list of Python files: glob
expansion, the recursive walk with directory-mode pruning, `--exclude`
matching, and realpath dedup.

This module never sees argparse. Root resolution — workspace autodiscovery,
binding parsed arguments — stays in the CLI adapter.

Failures raise a typed `TargetResolutionError`; the adapter is the only place
that calls `sys.exit`. `NoFilesToProcessError` is the one the adapter raises
itself, because "nothing to process" depends on whether the aggregate across
multiple roots is empty and on adapter-owned verbose reporting having already
run — this module still owns the type. (`_workspace.py` deliberately keeps its
own sys.exit-from-domain-code precedent; its failure modes share no
adapter-level catch point with these.)

One walk produces both the kept list and the excluded list. The earlier code
walked the tree a second time — without `--exclude` or `prune_dirs` applied —
just to diff against the first walk, which also mislabeled pruned-subtree files
as "excluded" though no `--exclude` pattern had matched them. Don't reintroduce
a second walk.
"""

import glob
import os
from collections.abc import Sequence
from dataclasses import dataclass

from mutate4py._glob_dialect import glob_match
from mutate4py._py_tree import walkable_dirs


class TargetResolutionError(Exception):
    """Base for target-resolution failures; carries the message and the
    process exit code the CLI adapter should use."""

    def __init__(self, message: str, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class PatternNoMatchError(TargetResolutionError):
    """A wildcard pattern matched no directories or .py files."""

    def __init__(self, pattern: str) -> None:
        super().__init__(f"pattern {pattern!r} matched no files.")


class PathNotFoundError(TargetResolutionError):
    """A literal (non-wildcard) path does not exist."""

    def __init__(self, pattern: str) -> None:
        super().__init__(f"[Errno 2] No such file or directory: {pattern!r}")


class NoFilesToProcessError(TargetResolutionError):
    """Nothing is left to process (empty tree, or everything excluded)."""

    def __init__(self) -> None:
        super().__init__("no Python files to process.")


@dataclass(frozen=True)
class WalkResult:
    """The .py files a walk kept, and the ones a `--exclude` pattern dropped."""

    kept: list[str]
    excluded: list[str]


def _is_excluded(path: str, patterns: Sequence[str]) -> bool:
    """True if path matches any --exclude glob (shared dialect, case-sensitive)."""
    return any(glob_match(path, pattern) for pattern in patterns)


def _is_target_py_file(path: str, exclude: Sequence[str]) -> bool:
    """True for a .py file that no --exclude pattern drops."""
    return path.endswith(".py") and not _is_excluded(path, exclude)


def _prune_walk_dirs(root: str, dirs: list[str], pruned_real: set[str]) -> list[str]:
    """Walkable subdirectories of root, minus any whose realpath is pruned."""
    return [d for d in walkable_dirs(dirs) if os.path.realpath(os.path.join(root, d)) not in pruned_real]


def _walk_py_files(directory: str, exclude: Sequence[str], pruned_real: set[str]) -> WalkResult:
    """Recursively walk directory, bucketing every .py file into kept or
    excluded in a single pass; non-.py files are dropped from both."""
    kept: list[str] = []
    excluded: list[str] = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = _prune_walk_dirs(root, dirs, pruned_real)
        for f in sorted(files):
            path = os.path.join(root, f)
            if not path.endswith(".py"):
                continue
            if _is_excluded(path, exclude):
                excluded.append(path)
            else:
                kept.append(path)
    return WalkResult(kept=kept, excluded=excluded)


def _collect_py_files(directory: str, exclude: Sequence[str] = (), prune_dirs: Sequence[str] = ()) -> WalkResult:
    """The .py files under a root, bucketed into kept and --exclude-dropped.

    The root may be a directory (walked recursively) or a single file (kept
    or excluded as-is) — the union path calls this
    uniformly over every resolved root.

    prune_dirs skips whole subtrees by path identity (os.path.realpath),
    not by glob pattern — used for [tool.uv.workspace].exclude, which names
    real directories that may themselves contain glob metacharacters — a
    literal "*" in a directory name must not be reinterpreted as a wildcard.
    """
    if not os.path.isdir(directory):
        if not directory.endswith(".py"):
            return WalkResult(kept=[], excluded=[])
        if _is_excluded(directory, exclude):
            return WalkResult(kept=[], excluded=[directory])
        return WalkResult(kept=[directory], excluded=[])
    pruned_real = {os.path.realpath(d) for d in prune_dirs}
    return _walk_py_files(directory, exclude, pruned_real)


_GLOB_CHARS = frozenset("*?[")


def _has_glob_chars(pattern: str) -> bool:
    """True if pattern needs filesystem expansion rather than literal lookup."""
    return any(c in _GLOB_CHARS for c in pattern)


def _expand_glob_pattern(pattern: str) -> list[str]:
    """Resolve a wildcard pattern to its matched dirs/.py files, sorted.

    Other matched files are dropped silently; raises if nothing survives,
    naming the pattern.
    """
    matches = sorted(glob.glob(pattern, recursive=True))
    kept = [m for m in matches if os.path.isdir(m) or m.endswith(".py")]
    if not kept:
        raise PatternNoMatchError(pattern)
    return kept


def _expand_literal_path(pattern: str) -> str:
    """Resolve a literal (non-wildcard) path; raises naming it if missing."""
    if not os.path.exists(pattern):
        raise PathNotFoundError(pattern)
    return pattern


def _expand_roots(patterns: Sequence[str]) -> list[str]:
    """Resolve positional patterns to root paths, in argument order.

    Every pattern is validated before any file is collected: a bad pattern
    anywhere in the list raises before dispatch, with none of the other
    patterns' files processed. Feeds both positional expansion and uv
    workspace `members`.
    """
    roots: list[str] = []
    for pattern in patterns:
        if _has_glob_chars(pattern):
            roots.extend(_expand_glob_pattern(pattern))
        else:
            roots.append(_expand_literal_path(pattern))
    return roots


def _dedup_by_realpath(files: list[str]) -> list[str]:
    """Drop later duplicates that resolve to the same real path; keep the
    first occurrence and the given order."""
    seen: set[str] = set()
    result = []
    for f in files:
        real = os.path.realpath(f)
        if real not in seen:
            seen.add(real)
            result.append(f)
    return result
