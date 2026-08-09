"""Target resolution (issue #38 gate 05): turns positional arguments into a
concrete list of Python files.

Glob-pattern expansion (shared dialect), the recursive walk with
directory-mode pruning, `--exclude` matching, and realpath dedup all live
here. Root resolution itself (workspace autodiscovery, binding parsed
arguments) stays in the CLI adapter — this module never sees argparse.

Failure modes raise a typed `TargetResolutionError` instead of exiting the
process; the adapter is the only place that calls `sys.exit`. The "nothing
to process" mode is the exception: it depends on whether an aggregate across
multiple roots is empty, and on adapter-owned verbose reporting having run
first, so the adapter raises `NoFilesToProcessError` itself once it has
finished collecting and reporting. This module still owns the error type.

A single walk produces both the kept list and the excluded list (files a
`--exclude` pattern dropped) — the old code walked the tree a second time,
without `--exclude` or `prune_dirs` applied, just to diff against the first
walk's result. That second walk also mislabeled pruned-subtree files as
"excluded" even though no `--exclude` pattern had matched them. One walk
fixes both.

Decision (ticket 05 AC): `_workspace.py` keeps its own sys.exit-from-domain-
code precedent for now rather than adopting this raise-not-exit contract.
Its failure modes (missing pyproject.toml, malformed TOML, a workspace key
that isn't a list of strings) are a different, self-contained concern with
no adapter-level catch to share; folding it into this ticket would extend
the diff without a clear justification. Revisit if a future ticket needs
`_workspace.py` errors to flow through the same catch point as these.
"""

import glob
import os
from collections.abc import Sequence
from dataclasses import dataclass

from mutate4py._glob_dialect import glob_match


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


_PRUNED_DIR_NAMES = {"__pycache__", "venv", "node_modules"}


def _walkable_dirs(dirs: list[str]) -> list[str]:
    """Sorted subdirectories to descend into.

    Prunes __pycache__, venv, node_modules, and any dot-directory (e.g.
    .git, .venv). build/ and dist/ are deliberately left walkable.
    """
    return sorted(d for d in dirs if d not in _PRUNED_DIR_NAMES and not d.startswith("."))


def _is_target_py_file(path: str, exclude: Sequence[str]) -> bool:
    """True for a .py file that no --exclude pattern drops."""
    return path.endswith(".py") and not _is_excluded(path, exclude)


def _prune_walk_dirs(root: str, dirs: list[str], pruned_real: set[str]) -> list[str]:
    """Walkable subdirectories of root, minus any whose realpath is pruned."""
    return [d for d in _walkable_dirs(dirs) if os.path.realpath(os.path.join(root, d)) not in pruned_real]


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
    or excluded as-is) — the union path (issue #22 item 15) calls this
    uniformly over every resolved root.

    prune_dirs skips whole subtrees by path identity (os.path.realpath),
    not by glob pattern — used for [tool.uv.workspace].exclude, which names
    real directories that may themselves contain glob metacharacters (phase
    B review: a literal "*" in a directory name must not be reinterpreted).
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

    Other matched files are dropped silently (issue #22 item 6); raises if
    nothing survives, naming the pattern (item 7).
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

    Every pattern is validated (item 7's fail-fast) before any file is
    collected: a bad pattern anywhere in the list raises before dispatch,
    with none of the other patterns' files processed. Feeds both positional
    expansion (this cycle) and uv workspace `members` (a later cycle).
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
    first occurrence and the given order (issue #22 item 14)."""
    seen: set[str] = set()
    result = []
    for f in files:
        real = os.path.realpath(f)
        if real not in seen:
            seen.add(real)
            result.append(f)
    return result
