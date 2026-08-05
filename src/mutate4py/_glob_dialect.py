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
    is_boundary_double_star = (
        j - i == 2 and _at_boundary(pattern, i - 1) and _at_boundary(pattern, j)
    )
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


# mutate4py-manifest-begin
# {"version":1,"tested_at":"2026-08-05T16:43:57Z","module_hash":"24e95f28268cd269c9f23bc5f9a3c8f1314104a00c25b12c7894e5f4dabfa427","functions":[{"id":"func/_at_boundary","name":"_at_boundary","line":13,"end_line":20,"hash":"fef8bb4af656a9c26734af90475a2aaac10dbea1328a04b81eeb92fd6445111d"},{"id":"func/_star_run_end","name":"_star_run_end","line":23,"end_line":29,"hash":"c86b4ecf54e3a191ea8537f37a2507d49a684324a672ca46d3bf8ca254947885"},{"id":"func/_translate_double_star","name":"_translate_double_star","line":32,"end_line":40,"hash":"fe0131423d779f85c29dab98d98fbf00cda17b411848b5ec391fc54382db1b77"},{"id":"func/_translate_star_run","name":"_translate_star_run","line":43,"end_line":51,"hash":"e917c59b1a760c872b094ce1f32122f4ef89a4debc7bd2326dde059762db567a"},{"id":"func/_translate","name":"_translate","line":54,"end_line":65,"hash":"342de62039374817eeeb79614e87ee2143af19568109f5107f7c10456376879b"},{"id":"func/_compile","name":"_compile","line":69,"end_line":70,"hash":"fb0ad9201424b0775f163117a7ae63826a9202f3c12a48d217d59cfff4e29d46"},{"id":"func/glob_match","name":"glob_match","line":73,"end_line":75,"hash":"53d6abbf0317cc21d8033adedc859baf0213fb248169cbc1cb59bb9802ff94cc"}]}
# mutate4py-manifest-end
