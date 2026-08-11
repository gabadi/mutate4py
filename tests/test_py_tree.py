"""Unit tests for _py_tree.py (shared project-tree walk pruning)."""

from mutate4py._py_tree import walkable_dirs


def test_walkable_dirs_sorts_and_drops_pycache():
    assert walkable_dirs(["sub", "__pycache__", "abc"]) == ["abc", "sub"]


def test_walkable_dirs_prunes_dot_dirs_venv_and_node_modules():
    """Issue #22 item 13: applies to ALL directory-mode walks, not just
    autodiscovered ones. build/ and dist/ are deliberately NOT pruned."""
    assert walkable_dirs(["sub", ".git", ".venv", "venv", "node_modules", "build", "dist"]) == [
        "build",
        "dist",
        "sub",
    ]
