"""Unit tests for the shared glob dialect (issue #22 item 4).

Dialect: `*` matches exactly one path segment (never crosses `/`); `**` matches
zero or more segments. Used by --exclude (this cycle) and, in a later cycle,
positional patterns and uv `members`/`exclude`.
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
