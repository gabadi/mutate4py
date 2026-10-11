"""Equivalent markers: `# mutate4py: equivalent <reason>` comments that accept a survivor."""

import io
import re
import tokenize

_MARKER_RE = re.compile(r"#\s*mutate4py:\s*equivalent(?:\s+(.*?))?(?:\s+#.*)?$")


class EquivalentMarkerError(ValueError):
    """An `# mutate4py: equivalent` marker with no reason (usage error, exit 2)."""


def marker_lines(source: str) -> dict[int, str]:
    """Map line -> reason for every marker comment in source. Never raises: an empty reason maps to "".

    Only COMMENT tokens are scanned, so `#` inside a string never counts.
    """
    markers: dict[int, str] = {}
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type != tokenize.COMMENT:
            continue
        match = _MARKER_RE.search(tok.string)
        if match is None:
            continue
        markers[tok.start[0]] = (match.group(1) or "").strip()
    return markers


def equivalent_markers(source: str) -> dict[int, str]:
    """Map line -> reason for every marker comment in source; raise on the first marker with no reason."""
    markers = marker_lines(source)
    for line, reason in markers.items():
        if not reason:
            raise EquivalentMarkerError(f"line {line}: '# mutate4py: equivalent' needs a reason")
    return markers
