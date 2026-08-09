"""Unit tests for mutate4py._target_resolution (issue #38 gate 05).

Assert on returned values and raised errors, not process exit and captured
stdout — this module never calls sys.exit or print (that's the CLI
adapter's job; see tests/test_main.py for adapter-level coverage of
verbose reporting and exit codes).
"""

import os

import pytest

from mutate4py._target_resolution import (
    NoFilesToProcessError,
    PatternNoMatchError,
    PathNotFoundError,
    WalkResult,
    _collect_py_files,
    _dedup_by_realpath,
    _expand_roots,
    _is_excluded,
    _is_target_py_file,
    _walkable_dirs,
)


def _make_pkg_tree(tmp_path) -> str:
    """pkg/{mod.py, __init__.py, sub/{deep.py, __init__.py}}; return pkg path."""
    d = tmp_path / "pkg"
    sub = d / "sub"
    sub.mkdir(parents=True)
    for p in (d / "mod.py", d / "__init__.py", sub / "deep.py", sub / "__init__.py"):
        p.write_text("x = 1\n")
    return str(d)


# ── error types ────────────────────────────────────────────────────────────


def test_pattern_no_match_error_carries_message_and_exit_code():
    exc = PatternNoMatchError("*.py")
    assert str(exc) == "pattern '*.py' matched no files."
    assert exc.exit_code == 2


def test_path_not_found_error_carries_message_and_exit_code():
    exc = PathNotFoundError("mod.py")
    assert str(exc) == "[Errno 2] No such file or directory: 'mod.py'"
    assert exc.exit_code == 2


def test_no_files_to_process_error_carries_message_and_exit_code():
    exc = NoFilesToProcessError()
    assert str(exc) == "no Python files to process."
    assert exc.exit_code == 2


# ── _collect_py_files: kept/excluded bucketing ──────────────────────────────


def test_collect_py_files_skips_pycache(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "mod.py").write_text("x = 1\n")
    cache = d / "__pycache__"
    cache.mkdir()
    (cache / "mod.cpython-312.pyc").write_text("")
    result = _collect_py_files(str(d))
    assert all("__pycache__" not in f for f in result.kept)
    assert any("mod.py" in f for f in result.kept)


def test_collect_py_files_ignores_non_py_files(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "mod.py").write_text("x = 1\n")
    (d / "README.md").write_text("docs")
    (d / "data.txt").write_text("data")
    result = _collect_py_files(str(d))
    assert result.kept == [str(d / "mod.py")]
    assert result.excluded == []


# ── multi-root union (issue #22): _collect_py_files also accepts a file root ──


def test_collect_py_files_root_may_be_a_single_py_file(tmp_path):
    """Issue #22 item 15's union formula calls _collect_py_files uniformly over
    every resolved root, whether the root is a directory or a single file."""
    p = tmp_path / "mod.py"
    p.write_text("x = 1\n")
    assert _collect_py_files(str(p)) == WalkResult(kept=[str(p)], excluded=[])


def test_collect_py_files_file_root_respects_exclude():
    result = _collect_py_files("pkg/mod.py", ["**/mod.py"])
    assert result.kept == []
    assert result.excluded == ["pkg/mod.py"]


def test_collect_py_files_file_root_non_py_is_neither_kept_nor_excluded(tmp_path):
    p = tmp_path / "README.md"
    p.write_text("docs\n")
    assert _collect_py_files(str(p)) == WalkResult(kept=[], excluded=[])


# ── _collect_py_files: prune_dirs (issue #22 phase B review #3) ────────────────
#
# [tool.uv.workspace].exclude names real directories, not glob patterns.
# prune_dirs matches them by path identity (realpath), not by re-encoding
# the literal path as a glob string — a directory literally named
# "some*dir" must not accidentally swallow a sibling "someXXXdir" the way
# a synthesized f"{d}/**" glob pattern would.


def test_collect_py_files_prune_dirs_skips_the_whole_subtree(tmp_path):
    d = tmp_path / "pkg"
    vendor = d / "vendor"
    vendor.mkdir(parents=True)
    (d / "a.py").write_text("x = 1\n")
    (vendor / "b.py").write_text("x = 2\n")
    result = _collect_py_files(str(d), prune_dirs=[str(vendor)])
    assert result.kept == [str(d / "a.py")]


def test_collect_py_files_prune_dirs_does_not_use_glob_matching(tmp_path):
    """A pruned directory containing a glob metacharacter must not affect
    an unrelated sibling whose name happens to match it as a pattern."""
    d = tmp_path / "pkg"
    starred = d / "some*dir"
    sibling = d / "someXXXdir"
    starred.mkdir(parents=True)
    sibling.mkdir(parents=True)
    (starred / "a.py").write_text("x = 1\n")
    (sibling / "b.py").write_text("x = 2\n")
    result = _collect_py_files(str(d), prune_dirs=[str(starred)])
    assert result.kept == [str(sibling / "b.py")]


def test_collect_py_files_prune_dirs_defaults_to_no_pruning(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "a.py").write_text("x = 1\n")
    assert _collect_py_files(str(d)).kept == [str(d / "a.py")]


# ── --exclude: collector filtering, one walk producing kept + excluded ─────────


def test_collect_py_files_exclude_matches_nested_path(tmp_path):
    d = _make_pkg_tree(tmp_path)
    result = _collect_py_files(d, ["**/sub/deep.py"])
    assert os.path.join(d, "sub", "deep.py") not in result.kept
    assert os.path.join(d, "sub", "deep.py") in result.excluded
    assert os.path.join(d, "mod.py") in result.kept
    assert os.path.join(d, "sub", "__init__.py") in result.kept


def test_collect_py_files_exclude_patterns_union_not_intersect(tmp_path):
    d = _make_pkg_tree(tmp_path)
    result = _collect_py_files(d, ["**/__init__.py", "**/sub/*.py"])
    # union: both patterns drop files, and a file matching only one is still dropped
    assert result.kept == [os.path.join(d, "mod.py")]


def test_collect_py_files_exclude_no_match_is_a_no_op(tmp_path):
    d = _make_pkg_tree(tmp_path)
    assert _collect_py_files(d, ["*/nothing_here.py"]).kept == _collect_py_files(d).kept


def test_collect_py_files_exclude_still_skips_pycache(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "mod.py").write_text("x = 1\n")
    cache = d / "__pycache__"
    cache.mkdir()
    (cache / "mod.cpython-312.py").write_text("x = 1\n")
    result = _collect_py_files(str(d), ["*/other.py"])
    assert result.kept == [str(d / "mod.py")]


def test_collect_py_files_single_walk_produces_kept_and_excluded_together(tmp_path):
    """The old implementation walked the tree a second time (without
    --exclude or prune_dirs applied) to discover what the first walk had
    dropped. One call now returns both lists from a single walk."""
    d = _make_pkg_tree(tmp_path)
    result = _collect_py_files(d, ["**/sub/deep.py"])
    assert set(result.kept) | set(result.excluded) == {
        os.path.join(d, "mod.py"),
        os.path.join(d, "__init__.py"),
        os.path.join(d, "sub", "__init__.py"),
        os.path.join(d, "sub", "deep.py"),
    }


def test_is_excluded_is_case_sensitive():
    assert _is_excluded("src/Mod.py", ["src/Mod.py"])
    assert not _is_excluded("src/Mod.py", ["src/mod.py"])


def test_is_excluded_single_star_does_not_cross_a_slash():
    """New dialect (issue #22 item 5): '*' matches one segment; '**/' is
    required to match at arbitrary depth, unlike the old fnmatch behavior."""
    assert not _is_excluded("a/b/tests/mod.py", ["*/tests/*"])
    assert _is_excluded("a/b/tests/mod.py", ["**/tests/*"])


def test_is_target_py_file_requires_a_py_suffix():
    assert _is_target_py_file("pkg/mod.py", ())
    assert not _is_target_py_file("pkg/README.md", ())
    assert not _is_target_py_file("pkg/mod.py", ["*/mod.py"])


def test_walkable_dirs_sorts_and_drops_pycache():
    assert _walkable_dirs(["sub", "__pycache__", "abc"]) == ["abc", "sub"]


def test_walkable_dirs_prunes_dot_dirs_venv_and_node_modules():
    """Issue #22 item 13: applies to ALL directory-mode walks, not just
    autodiscovered ones. build/ and dist/ are deliberately NOT pruned."""
    assert _walkable_dirs(["sub", ".git", ".venv", "venv", "node_modules", "build", "dist"]) == [
        "build",
        "dist",
        "sub",
    ]


# ── multi-root positionals (issue #22): _expand_roots ──────────────────────────


def test_expand_roots_literal_directory_is_kept_as_is(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    assert _expand_roots([str(d)]) == [str(d)]


def test_expand_roots_literal_file_is_kept_as_is(tmp_path):
    p = tmp_path / "mod.py"
    p.write_text("x = 1\n")
    assert _expand_roots([str(p)]) == [str(p)]


def test_expand_roots_literal_missing_path_raises_naming_it():
    with pytest.raises(PathNotFoundError) as exc:
        _expand_roots(["/no/such/path.py"])
    assert "/no/such/path.py" in str(exc.value)
    assert "No such file or directory" in str(exc.value)
    assert exc.value.exit_code == 2


def test_expand_roots_glob_pattern_expands_to_matches(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "a.py").write_text("x = 1\n")
    (d / "b.py").write_text("x = 2\n")
    roots = _expand_roots([str(d / "*.py")])
    assert sorted(roots) == sorted([str(d / "a.py"), str(d / "b.py")])


def test_expand_roots_glob_pattern_keeps_directories_and_py_only(tmp_path):
    """Issue #22 item 6: a directory and .py files matched by a pattern
    survive; a non-.py file matched by the same pattern is dropped silently."""
    d = tmp_path / "pkg"
    sub = d / "sub"
    sub.mkdir(parents=True)
    (d / "a.py").write_text("x = 1\n")
    (d / "README.md").write_text("docs\n")
    roots = _expand_roots([str(d / "*")])
    assert sorted(roots) == sorted([str(d / "a.py"), str(sub)])


def test_expand_roots_glob_pattern_matching_nothing_raises_naming_pattern():
    with pytest.raises(PatternNoMatchError) as exc:
        _expand_roots(["/no/such/dir/*.py"])
    assert "/no/such/dir/*.py" in str(exc.value)
    assert exc.value.exit_code == 2


def test_expand_roots_pattern_matching_only_non_py_files_raises(tmp_path):
    """Every glob match filtered out (all non-.py, non-dir) counts as no match."""
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "README.md").write_text("docs\n")
    with pytest.raises(PatternNoMatchError):
        _expand_roots([str(d / "*.md")])


def test_expand_roots_preserves_argument_order(tmp_path):
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    first.write_text("x = 1\n")
    second.write_text("x = 2\n")
    assert _expand_roots([str(second), str(first)]) == [str(second), str(first)]


# ── multi-root positionals (issue #22): dedup by realpath ──────────────────────


def test_dedup_by_realpath_drops_a_repeated_path_keeping_the_first():
    assert _dedup_by_realpath(["a.py", "b.py", "a.py"]) == ["a.py", "b.py"]


def test_dedup_by_realpath_collapses_symlink_aliases(tmp_path):
    real = tmp_path / "real.py"
    real.write_text("x = 1\n")
    link = tmp_path / "link.py"
    link.symlink_to(real)
    assert _dedup_by_realpath([str(real), str(link)]) == [str(real)]
