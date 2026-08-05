"""The shared glob dialect (issue #22 item 4).

`*` matches exactly one path segment and never crosses `/`; `**` matches zero
or more segments. A small hand-rolled translator to regex, not a general glob
engine: `pathlib.PurePath.full_match` (which has this dialect built in) is
3.13+, and this project supports 3.10+.
"""

import functools
import re


def _translate(pattern: str) -> str:
    """Translate one dialect pattern into a regex string (unanchored body)."""
    out: list[str] = []
    i, n = 0, len(pattern)
    while i < n:
        if pattern[i : i + 2] == "**":
            i += 2
            if i < n and pattern[i] == "/":
                i += 1
                out.append("(?:.*/)?")
            else:
                out.append(".*")
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
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
# {"version":1,"tested_at":"2026-08-05T13:44:54Z","module_hash":"7493871ec4949b219680cd77f0f4e652ad5eccfd9b2857d48778bda9d0138b08","functions":[{"id":"func/_translate","name":"_translate","line":13,"end_line":31,"hash":"27ef45802339047ed621b8b5458e9c56f72685dc5a11e3920309c28db20b7a55"},{"id":"func/_compile","name":"_compile","line":35,"end_line":36,"hash":"fb0ad9201424b0775f163117a7ae63826a9202f3c12a48d217d59cfff4e29d46"},{"id":"func/glob_match","name":"glob_match","line":39,"end_line":41,"hash":"53d6abbf0317cc21d8033adedc859baf0213fb248169cbc1cb59bb9802ff94cc"}]}
# mutate4py-manifest-end
