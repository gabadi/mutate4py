"""Unit tests for the shared glob dialect (issue #22 item 4).

Dialect: `*` matches exactly one path segment (never crosses `/`); `**` matches
zero or more segments, but only when it stands alone as a whole `/`-bounded
path component — glued to literal text it degrades to a same-segment
wildcard. Used by --exclude (this cycle) and, in a later cycle, uv
`members`/`exclude` (positional patterns are expanded by stdlib
`glob.glob`, not this matcher).
"""

from mutate4py._glob_dialect import glob_match


def test_literal_pattern_matches_identical_path():
    assert glob_match("src/mod.py", "src/mod.py")


def test_literal_pattern_does_not_match_different_path():
    assert not glob_match("src/mod.py", "src/other.py")


def test_single_star_matches_one_segment():
    assert glob_match("src/mod.py", "*/mod.py")


def test_single_star_does_not_cross_a_slash():
    # Two segments ("src" and "sub") sit between the pattern's fixed ends;
    # a single '*' must not absorb the extra '/'.
    assert not glob_match("src/sub/mod.py", "*/mod.py")


def test_single_star_matches_within_final_segment():
    assert glob_match("src/mod.py", "src/*.py")
    assert not glob_match("src/sub/mod.py", "src/*.py")


def test_double_star_matches_zero_segments():
    assert glob_match("mod.py", "**/mod.py")


def test_double_star_matches_many_segments():
    assert glob_match("a/b/c/mod.py", "**/mod.py")


def test_double_star_matches_at_the_end():
    assert glob_match("src/a/b/mod.py", "src/**")


def test_double_star_at_the_end_requires_the_written_slash():
    # The pattern's own '/' is literal text the candidate must contain too;
    # "src/**" does not fold back to matching bare "src".
    assert not glob_match("src", "src/**")


def test_double_star_sandwiched_between_literals():
    assert glob_match("a/tests/b.py", "**/tests/**")
    assert glob_match("tests/b.py", "**/tests/**")
    assert glob_match("a/b/tests/c/d.py", "**/tests/**")


def test_double_star_sandwiched_requires_the_literal_segment():
    assert not glob_match("a/b/other/c.py", "**/tests/**")


def test_matching_is_case_sensitive():
    assert glob_match("src/Mod.py", "src/Mod.py")
    assert not glob_match("src/Mod.py", "src/mod.py")


def test_regex_special_characters_in_pattern_are_literal():
    assert glob_match("src/a.py", "src/a.py")
    assert not glob_match("src/aXpy", "src/a.py")


def test_double_star_glued_to_literal_text_does_not_cross_a_slash():
    """'**' only gets the "zero or more segments" meaning when it stands
    alone as a whole path component; glued to "foo" it is not a boundary
    component and must behave like an ordinary same-segment wildcard,
    matching stdlib glob.glob's own treatment of "foo**bar"."""
    assert not glob_match("foo/x/y/bar", "foo**bar")
    assert glob_match("fooXbar", "foo**bar")


def test_double_star_glued_before_a_slash_still_requires_the_slash():
    """ "foo**/bar" is not a boundary "**" component (it's glued to "foo"),
    so it must not fold the following '/' into an optional zero-segment
    match — it must not match "foobar" with no slash at all."""
    assert not glob_match("foobar", "foo**/bar")
    assert glob_match("fooX/bar", "foo**/bar")
