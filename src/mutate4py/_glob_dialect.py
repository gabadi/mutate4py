"""The shared glob dialect (issue #22 item 4).

`*` matches exactly one path segment and never crosses `/`; `**` matches zero
or more segments. A small hand-rolled translator to regex, not a general glob
engine: `pathlib.PurePath.full_match` (which has this dialect built in) is
3.13+, and this project supports 3.11+.
"""

import functools
import re


def _at_boundary(pattern: str, idx: int) -> bool:
    """True if idx sits before the start, past the end, or on a '/'.

    Used on both sides of a run of stars to decide whether it is a whole
    `/`-bounded path component (eligible for "**" semantics) or glued to
    literal text (must degrade to a same-segment wildcard).
    """
    return idx < 0 or idx >= len(pattern) or pattern[idx] == "/"


def _star_run_end(pattern: str, i: int) -> int:
    """Index just past the run of consecutive '*' starting at i."""
    j = i
    n = len(pattern)
    while j < n and pattern[j] == "*":
        j += 1
    return j


def _translate_double_star(pattern: str, j: int) -> tuple[str, int]:
    """Translate a whole-component '**' ending at j; returns (regex, new i).

    Swallows a following '/' into the same optional group so a boundary
    "**" can also match zero segments.
    """
    if j < len(pattern) and pattern[j] == "/":
        return "(?:.*/)?", j + 1
    return ".*", j


def _translate_star_run(pattern: str, i: int) -> tuple[str, int]:
    """Translate a run of consecutive '*' starting at i; returns (regex, new i)."""
    j = _star_run_end(pattern, i)
    is_boundary_double_star = j - i == 2 and _at_boundary(pattern, i - 1) and _at_boundary(pattern, j)
    if is_boundary_double_star:
        return _translate_double_star(pattern, j)
    return "[^/]*", j


def _translate(pattern: str) -> str:
    """Translate one dialect pattern into a regex string (unanchored body)."""
    out: list[str] = []
    i, n = 0, len(pattern)
    while i < n:
        if pattern[i] == "*":
            piece, i = _translate_star_run(pattern, i)
            out.append(piece)
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return "".join(out)


@functools.lru_cache(maxsize=None)
def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(_translate(pattern) + r"\Z")


def glob_match(path: str, pattern: str) -> bool:
    """True if path matches pattern under the shared dialect (case-sensitive)."""
    return _compile(pattern).match(path) is not None
