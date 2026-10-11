"""Tests for the equivalent marker: the parser and its effect on a re-run.

The marker is a comment `# mutate4py: equivalent <reason>` on the mutated line.
Only COMMENT tokens count, so the text inside a string never does.
"""

import pytest

from mutate4py._equivalent import EquivalentMarkerError, equivalent_markers
from mutate4py._manifest import build_manifest

_TESTED_AT = "2026-01-01T00:00:00Z"


@pytest.mark.unit
def test_marker_maps_line_to_reason():
    src = "def f(a, b):\n    return a > b  # mutate4py: equivalent same for all inputs\n"
    assert equivalent_markers(src) == {2: "same for all inputs"}


@pytest.mark.unit
def test_marker_after_other_comment_text():
    src = "def f(a, b):\n    return a > b  # noqa  # mutate4py: equivalent ok\n"
    assert equivalent_markers(src) == {2: "ok"}


@pytest.mark.unit
def test_marker_reason_stops_at_next_comment():
    src = "def f(a, b):\n    return a > b  # mutate4py: equivalent ok  # noqa\n"
    assert equivalent_markers(src) == {2: "ok"}


@pytest.mark.unit
def test_empty_reason_raises_with_line():
    src = "def f(a, b):\n    return a > b  # mutate4py: equivalent\n"
    with pytest.raises(EquivalentMarkerError, match="line 2"):
        equivalent_markers(src)


@pytest.mark.unit
def test_whitespace_reason_raises():
    src = "def f(a, b):\n    return a > b  # mutate4py: equivalent    \n"
    with pytest.raises(EquivalentMarkerError, match="line 2"):
        equivalent_markers(src)


@pytest.mark.unit
def test_unrelated_comments_ignored():
    src = "# mutate4py-manifest-begin\n# mutate4py: other\n# mutate4py: equivalentfoo\nx = 1\n"
    assert equivalent_markers(src) == {}


@pytest.mark.unit
def test_marker_text_inside_string_ignored():
    src = 'x = "# mutate4py: equivalent reason"\n'
    assert equivalent_markers(src) == {}


@pytest.mark.unit
def test_marker_keeps_unit_hash():
    plain = "def f(a, b):\n    return a > b\n"
    marked = "def f(a, b):\n    return a > b  # mutate4py: equivalent same for all inputs\n"
    plain_fns = build_manifest(plain, tested_at=_TESTED_AT)["functions"]
    marked_fns = build_manifest(marked, tested_at=_TESTED_AT)["functions"]
    assert [f["hash"] for f in marked_fns] == [f["hash"] for f in plain_fns]


@pytest.mark.unit
def test_marker_lines_keeps_empty_reason_without_raising():
    from mutate4py._equivalent import marker_lines

    assert marker_lines("x = 1  # mutate4py: equivalent\n") == {1: ""}
