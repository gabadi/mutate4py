"""Unit tests for uv workspace autodiscovery (issue #22 items 3, 8-12).

Test seam: unit level on the resolution functions (_find_pyproject,
_discover_workspace_roots, _workspace_exclude_dirs). CLI-level exit
codes/messages are covered separately in tests/test_main.py.
"""

import os

import pytest

from mutate4py._workspace import (
    _discover_workspace_roots,
    _find_pyproject,
    _workspace_exclude_dirs,
)


def _write(path, content: str) -> None:
    path.write_text(content)


def _workspace_pyproject(members=None, exclude=None) -> str:
    """A [tool.uv.workspace] pyproject.toml body."""
    lines = ["[tool.uv.workspace]"]
    if members is not None:
        items = ", ".join(f'"{m}"' for m in members)
        lines.append(f"members = [{items}]")
    if exclude is not None:
        items = ", ".join(f'"{e}"' for e in exclude)
        lines.append(f"exclude = [{items}]")
    return "\n".join(lines) + "\n"


def _package_pyproject(name: str = "pkg") -> str:
    """A plain (non-workspace) pyproject.toml body, as a member package has."""
    return f'[project]\nname = "{name}"\nversion = "0.1.0"\n'


# ── _find_pyproject: the ancestor climb ────────────────────────────────────────


def test_find_pyproject_finds_it_in_the_starting_directory(tmp_path):
    _write(tmp_path / "pyproject.toml", _workspace_pyproject())
    assert _find_pyproject(str(tmp_path)) == str(tmp_path / "pyproject.toml")


def test_find_pyproject_climbs_to_the_nearest_ancestor(tmp_path):
    _write(tmp_path / "pyproject.toml", _workspace_pyproject())
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    assert _find_pyproject(str(deep)) == str(tmp_path / "pyproject.toml")


def test_find_pyproject_returns_none_when_none_exists_upward(tmp_path):
    # tmp_path is deep under the OS temp root; none of its real ancestors
    # (temp dir, /, etc.) carry a pyproject.toml in a normal environment.
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    assert _find_pyproject(str(isolated)) is None


# ── _discover_workspace_roots: single-root and multi-member workspaces ─────────


def test_discover_single_root_workspace_with_no_members(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    _write(ws / "pyproject.toml", _workspace_pyproject())
    monkeypatch.chdir(ws)
    assert _discover_workspace_roots() == [str(ws)]


def test_discover_multi_member_workspace(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    pkgs = ws / "pkgs"
    a, b = pkgs / "a", pkgs / "b"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    _write(ws / "pyproject.toml", _workspace_pyproject(members=["pkgs/*"]))
    _write(a / "pyproject.toml", _package_pyproject("a"))
    _write(b / "pyproject.toml", _package_pyproject("b"))
    monkeypatch.chdir(ws)
    assert _discover_workspace_roots() == [str(ws), str(a), str(b)]


def test_discover_nested_glob_pattern_in_members(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    g1_pkg = ws / "groups" / "g1" / "pkgs" / "one"
    g2_pkg = ws / "groups" / "g2" / "pkgs" / "two"
    g1_pkg.mkdir(parents=True)
    g2_pkg.mkdir(parents=True)
    _write(
        ws / "pyproject.toml",
        _workspace_pyproject(members=["groups/*/pkgs/*"]),
    )
    _write(g1_pkg / "pyproject.toml", _package_pyproject("one"))
    _write(g2_pkg / "pyproject.toml", _package_pyproject("two"))
    monkeypatch.chdir(ws)
    assert _discover_workspace_roots() == [str(ws), str(g1_pkg), str(g2_pkg)]


def test_member_matched_by_glob_without_pyproject_is_skipped_silently(
    tmp_path, monkeypatch
):
    ws = tmp_path / "ws"
    pkgs = ws / "pkgs"
    has_one, missing_one = pkgs / "has", pkgs / "missing"
    has_one.mkdir(parents=True)
    missing_one.mkdir(parents=True)
    _write(ws / "pyproject.toml", _workspace_pyproject(members=["pkgs/*"]))
    _write(has_one / "pyproject.toml", _package_pyproject())
    # "missing" has no pyproject.toml at all.
    monkeypatch.chdir(ws)
    assert _discover_workspace_roots() == [str(ws), str(has_one)]


def test_member_declaring_its_own_workspace_table_is_included_normally(
    tmp_path, monkeypatch
):
    ws = tmp_path / "ws"
    member = ws / "pkgs" / "a"
    member.mkdir(parents=True)
    _write(ws / "pyproject.toml", _workspace_pyproject(members=["pkgs/*"]))
    _write(member / "pyproject.toml", _workspace_pyproject())  # its own table
    monkeypatch.chdir(ws)
    assert _discover_workspace_roots() == [str(ws), str(member)]


# ── [tool.uv.workspace].exclude: prunes both the member list and the walk ──────


def test_exclude_prunes_an_excluded_member_from_the_roots(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    pkgs = ws / "pkgs"
    a, b = pkgs / "a", pkgs / "b"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    _write(
        ws / "pyproject.toml",
        _workspace_pyproject(members=["pkgs/*"], exclude=["pkgs/b"]),
    )
    _write(a / "pyproject.toml", _package_pyproject("a"))
    _write(b / "pyproject.toml", _package_pyproject("b"))
    monkeypatch.chdir(ws)
    assert _discover_workspace_roots() == [str(ws), str(a)]


def test_workspace_exclude_dirs_resolves_relative_to_the_workspace_root(
    tmp_path, monkeypatch
):
    ws = tmp_path / "ws"
    vendor = ws / "vendor"
    vendor.mkdir(parents=True)
    _write(ws / "pyproject.toml", _workspace_pyproject(exclude=["vendor"]))
    monkeypatch.chdir(ws)
    assert _workspace_exclude_dirs() == [str(vendor)]


# ── members resolve against the workspace root, not cwd (review point 1) ───────


def test_members_glob_resolves_against_workspace_root_not_cwd(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    pkgs = ws / "pkgs"
    a, b = pkgs / "a", pkgs / "b"
    other = ws / "other"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    other.mkdir(parents=True)
    _write(ws / "pyproject.toml", _workspace_pyproject(members=["pkgs/*"]))
    _write(a / "pyproject.toml", _package_pyproject("a"))
    _write(b / "pyproject.toml", _package_pyproject("b"))
    # cwd is a workspace subdirectory that is NOT the workspace root; if
    # members were (wrongly) resolved against cwd, "pkgs/*" would match
    # nothing from here.
    monkeypatch.chdir(other)
    assert _discover_workspace_roots() == [str(ws), str(a), str(b)]


# ── the ancestor climb stops at the FIRST pyproject.toml (review point 2) ──────


def test_climb_stops_at_first_pyproject_toml_even_without_a_workspace_table(
    tmp_path, monkeypatch, capsys
):
    outer = tmp_path / "outer"
    member = outer / "member"
    member.mkdir(parents=True)
    _write(outer / "pyproject.toml", _workspace_pyproject(members=["member"]))
    _write(member / "pyproject.toml", _package_pyproject())  # no workspace table
    # Running from inside the member finds the member's OWN pyproject.toml
    # first and must error there, not keep climbing to the real workspace
    # root above it (mirrors uv's find_workspace).
    monkeypatch.chdir(member)
    with pytest.raises(SystemExit) as exc:
        _discover_workspace_roots()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert str(member / "pyproject.toml") in err
    assert "[tool.uv.workspace]" in err


# ── error messages (item 12): two distinct, path-naming cases ──────────────────


def test_no_pyproject_found_names_the_search_start(tmp_path, monkeypatch, capsys):
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    monkeypatch.chdir(isolated)
    with pytest.raises(SystemExit) as exc:
        _discover_workspace_roots()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert str(isolated) in err
    assert "pyproject.toml" in err


def test_pyproject_without_workspace_table_names_that_path(
    tmp_path, monkeypatch, capsys
):
    d = tmp_path / "plain"
    d.mkdir()
    _write(d / "pyproject.toml", _package_pyproject())
    monkeypatch.chdir(d)
    with pytest.raises(SystemExit) as exc:
        _discover_workspace_roots()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert str(d / "pyproject.toml") in err
    assert "[tool.uv.workspace]" in err


# ── ordering: workspace root first, then members (item 15) ─────────────────────


def test_roots_start_with_the_workspace_root(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    member = ws / "m"
    member.mkdir(parents=True)
    _write(ws / "pyproject.toml", _workspace_pyproject(members=["m"]))
    _write(member / "pyproject.toml", _package_pyproject())
    monkeypatch.chdir(ws)
    roots = _discover_workspace_roots()
    assert roots[0] == str(ws)
    assert os.path.abspath(roots[0]) == roots[0]
