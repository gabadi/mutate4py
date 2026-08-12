"""CLI-level integration tests for directory/glob/union dispatch (__main__).

Split out of test_main.py by testing concern (issue #38 gate 17): __main__.py
itself has no further source to extract (already 184 lines), so this file
groups test_main.py's subprocess/main()-level integration coverage of
_dispatch.py's directory, glob, union, and workspace-autodiscovery behavior —
the surviving integration counterpart of what gate 11 already unit-tested
directly in tests/test_dispatch.py. Deliberately not merged into
test_dispatch.py, whose own precedent (from gate 11) is direct unit tests of
the extracted dispatch functions only.
"""

import os
import subprocess
import sys

import pytest


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _run_cli_path(path: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "mutate4py", path] + list(args),
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": os.path.join(REPO_ROOT, "src")},
        timeout=30,
    )


def _run_cli_in(cwd: str, *args: str) -> subprocess.CompletedProcess:
    """Run mutate4py with no positional path, from a given cwd (for
    zero-positional autodiscovery tests, issue #22 items 3, 8-12)."""
    return subprocess.run(
        [sys.executable, "-m", "mutate4py"] + list(args),
        capture_output=True,
        text=True,
        cwd=cwd,
        env={**os.environ, "PYTHONPATH": os.path.join(REPO_ROOT, "src")},
        timeout=30,
    )


# ── directory support ─────────────────────────────────────────────────────────


def _make_src_dir(tmp_path, files: dict[str, str]) -> str:
    """Create a directory with given {filename: content} mapping; return dir path."""
    d = tmp_path / "src"
    d.mkdir()
    for name, content in files.items():
        (d / name).write_text(content)
    return str(d)


@pytest.mark.integration
def test_directory_run_mode_attempts_run_on_files(tmp_path):
    d = _make_src_dir(tmp_path, {"a.py": "x = 1\n"})
    result = _run_cli_path(d, "--pytest-args", "--collect-only -q tests/test_cmd.py", "--no-fork")
    assert "run mode requires a single file, not a directory" not in result.stderr


@pytest.mark.integration
def test_directory_check_manifest_all_missing_exits_1(tmp_path):
    d = _make_src_dir(tmp_path, {"a.py": "def f(): pass\n", "b.py": "def g(): pass\n"})
    result = _run_cli_path(d, "--check-manifest")
    assert result.returncode == 1
    assert "Manifest missing:" in result.stdout


@pytest.mark.integration
def test_directory_check_manifest_all_current_exits_0(tmp_path):
    d = tmp_path / "src"
    d.mkdir()
    for name in ("a.py", "b.py"):
        p = d / name
        p.write_text("def f(): pass\n")
        setup = _run_cli_path(str(p), "--update-manifest")
        assert setup.returncode == 0

    result = _run_cli_path(str(d), "--check-manifest")
    assert result.returncode == 0
    assert "Manifest current:" in result.stdout


@pytest.mark.integration
def test_directory_check_manifest_one_stale_exits_1(tmp_path):
    d = tmp_path / "src"
    d.mkdir()
    p_a = d / "a.py"
    p_a.write_text("def f(): pass\n")
    setup = _run_cli_path(str(p_a), "--update-manifest")
    assert setup.returncode == 0

    p_b = d / "b.py"
    p_b.write_text("def g(): pass\n")

    result = _run_cli_path(str(d), "--check-manifest")
    assert result.returncode == 1
    assert "Manifest missing:" in result.stdout
    assert "Manifest current:" in result.stdout


@pytest.mark.integration
def test_directory_check_manifest_excluded_file_ignored_exits_0(tmp_path):
    d = tmp_path / "src"
    d.mkdir()
    p_a = d / "a.py"
    p_a.write_text("def f(): pass\n")
    setup = _run_cli_path(str(p_a), "--update-manifest")
    assert setup.returncode == 0

    (d / "b.py").write_text("def g(): pass\n")

    result = _run_cli_path(str(d), "--check-manifest", "--exclude", "**/b.py")
    assert result.returncode == 0
    assert "Manifest current:" in result.stdout
    assert "b.py" not in result.stdout


@pytest.mark.integration
def test_directory_check_manifest_stale_survivor_exits_1(tmp_path):
    """One non-excluded stale file still fails, reporting only that file."""
    d = tmp_path / "src"
    d.mkdir()
    p_a = d / "a.py"
    p_a.write_text("def f(): pass\n")
    setup = _run_cli_path(str(p_a), "--update-manifest")
    assert setup.returncode == 0

    (d / "b.py").write_text("def g(): pass\n")
    (d / "c.py").write_text("def h(): pass\n")

    result = _run_cli_path(str(d), "--check-manifest", "--exclude", "**/c.py")
    assert result.returncode == 1
    assert "Manifest missing:" in result.stdout
    assert "b.py" in result.stdout
    assert "c.py" not in result.stdout


@pytest.mark.integration
def test_directory_all_files_excluded_exits_2(tmp_path):
    d = _make_src_dir(tmp_path, {"a.py": "def f(): pass\n", "b.py": "def g(): pass\n"})
    result = _run_cli_path(d, "--check-manifest", "--exclude", "**/*.py")
    assert result.returncode == 2
    assert "error: no Python files to process." in result.stderr
    assert result.stdout == ""


@pytest.mark.integration
def test_directory_with_no_py_files_exits_2(tmp_path):
    d = tmp_path / "src"
    d.mkdir()
    (d / "README.md").write_text("docs\n")
    result = _run_cli_path(str(d), "--check-manifest")
    assert result.returncode == 2
    assert "error: no Python files to process." in result.stderr


@pytest.mark.integration
def test_directory_all_files_excluded_exits_2_in_scan_mode(tmp_path):
    d = _make_src_dir(tmp_path, {"a.py": "x = 1\n"})
    result = _run_cli_path(d, "--scan", "--exclude", "**/*.py")
    assert result.returncode == 2
    assert "error: no Python files to process." in result.stderr


@pytest.mark.integration
def test_directory_all_files_excluded_exits_2_in_update_manifest_mode(tmp_path):
    d = _make_src_dir(tmp_path, {"a.py": "x = 1\n"})
    result = _run_cli_path(d, "--update-manifest", "--exclude", "**/*.py")
    assert result.returncode == 2
    assert "error: no Python files to process." in result.stderr
    assert "mutate4py-manifest-begin" not in (tmp_path / "src" / "a.py").read_text()


@pytest.mark.integration
def test_directory_all_files_excluded_exits_2_in_run_mode(tmp_path):
    """Run mode bails before acquiring coverage or timing a baseline."""
    d = _make_src_dir(tmp_path, {"a.py": "x = 1\n"})
    result = _run_cli_path(d, "--exclude", "**/*.py")
    assert result.returncode == 2
    assert "error: no Python files to process." in result.stderr


@pytest.mark.integration
def test_directory_verbose_reports_excluded_files(tmp_path):
    d = _make_src_dir(tmp_path, {"a.py": "def f(): pass\n", "b.py": "def g(): pass\n"})
    result = _run_cli_path(d, "--check-manifest", "--exclude", "**/b.py", "--verbose")
    assert f"Excluded: {os.path.join(d, 'b.py')}" in result.stdout
    assert "Excluded: " + os.path.join(d, "a.py") not in result.stdout


@pytest.mark.integration
def test_directory_excluded_files_are_silent_without_verbose(tmp_path):
    d = _make_src_dir(tmp_path, {"a.py": "def f(): pass\n", "b.py": "def g(): pass\n"})
    result = _run_cli_path(d, "--check-manifest", "--exclude", "**/b.py")
    assert "Excluded:" not in result.stdout
    assert "b.py" not in result.stdout


@pytest.mark.integration
def test_directory_two_exclude_flags_both_take_effect(tmp_path):
    """Two separate --exclude flags on argv both apply (action="append"), not just
    the last one (which is what a dropped/misconfigured `dest` would leave)."""
    d = _make_pkg_tree(tmp_path)
    result = _run_cli_path(
        d,
        "--check-manifest",
        "--exclude",
        "**/__init__.py",
        "--exclude",
        "**/sub/deep.py",
        "--verbose",
    )
    assert f"Excluded: {os.path.join(d, '__init__.py')}" in result.stdout
    assert f"Excluded: {os.path.join(d, 'sub', '__init__.py')}" in result.stdout
    assert f"Excluded: {os.path.join(d, 'sub', 'deep.py')}" in result.stdout
    assert "Excluded: " + os.path.join(d, "mod.py") not in result.stdout
    assert "Manifest missing: " + os.path.join(d, "mod.py") in result.stdout


@pytest.mark.integration
def test_single_file_matching_exclude_exits_2(tmp_path):
    p = tmp_path / "mod.py"
    p.write_text("def f(): pass\n")
    result = _run_cli_path(str(p), "--check-manifest", "--exclude", "**/mod.py")
    assert result.returncode == 2
    assert "error: no Python files to process." in result.stderr
    assert "Manifest missing:" not in result.stdout


@pytest.mark.integration
def test_missing_single_file_reports_not_found_even_when_excluded(tmp_path):
    """A path that does not exist reports the real error, never 'excluded'."""
    missing = str(tmp_path / "mod.py")
    result = _run_cli_path(missing, "--check-manifest", "--exclude", "**/mod.py")
    assert result.returncode == 2
    assert "No such file or directory" in result.stderr
    assert "no Python files to process" not in result.stderr


@pytest.mark.integration
def test_existing_single_file_matching_exclude_reports_exclusion_not_not_found(
    tmp_path,
):
    """The companion ordering: an existing target that matches is an exclusion."""
    p = tmp_path / "mod.py"
    p.write_text("def f(): pass\n")
    result = _run_cli_path(str(p), "--check-manifest", "--exclude", "**/mod.py")
    assert result.returncode == 2
    assert "error: no Python files to process." in result.stderr
    assert "No such file or directory" not in result.stderr


@pytest.mark.integration
def test_single_file_verbose_reports_the_excluded_target(tmp_path):
    p = tmp_path / "mod.py"
    p.write_text("def f(): pass\n")
    result = _run_cli_path(str(p), "--check-manifest", "--exclude", "**/mod.py", "--verbose")
    assert f"Excluded: {p}" in result.stdout


@pytest.mark.integration
def test_single_file_not_matching_exclude_is_a_no_op(tmp_path):
    p = tmp_path / "mod.py"
    p.write_text("def f(): pass\n")
    result = _run_cli_path(str(p), "--check-manifest", "--exclude", "**/other.py")
    assert result.returncode == 1
    assert "Manifest missing:" in result.stdout


@pytest.mark.integration
def test_directory_update_manifest_processes_all_files(tmp_path):
    d = _make_src_dir(tmp_path, {"a.py": "def f(): pass\n", "b.py": "def g(): pass\n"})
    result = _run_cli_path(d, "--update-manifest")
    assert result.returncode == 0
    for name in ("a.py", "b.py"):
        content = (tmp_path / "src" / name).read_text()
        assert "mutate4py-manifest-begin" in content


@pytest.mark.integration
def test_directory_scan_processes_all_files(tmp_path):
    d = _make_src_dir(tmp_path, {"a.py": "x = a > b\n", "b.py": "y = c + d\n"})
    result = _run_cli_path(d, "--scan")
    assert result.returncode == 0
    assert result.stdout.count("Mutation scan:") == 2


@pytest.mark.integration
def test_directory_manifest_file_writes_one_sidecar_per_file(tmp_path):
    """--manifest-file works for a directory target: each source file gets its
    own <file>.manifest.json, and no source file gains an embedded footer."""
    import json

    d = _make_src_dir(
        tmp_path,
        {
            "a.py": "def f(a, b):\n    return a > b\n",
            "b.py": "def g(c, d):\n    return c + d\n",
        },
    )

    result = _run_cli_path(d, "--update-manifest", "--manifest-file")

    assert result.returncode == 0
    a_path = str(tmp_path / "src" / "a.py")
    b_path = str(tmp_path / "src" / "b.py")
    for path in (a_path, b_path):
        assert "mutate4py-manifest-begin" not in open(path).read()

    a_sidecar = json.loads(open(a_path + ".manifest.json").read())
    b_sidecar = json.loads(open(b_path + ".manifest.json").read())
    assert a_sidecar["functions"][0]["id"] == "func/f"
    assert b_sidecar["functions"][0]["id"] == "func/g"

    check_result = _run_cli_path(d, "--check-manifest", "--manifest-file")
    assert check_result.returncode == 0
    assert check_result.stdout.count("Manifest current:") == 2


def _make_pkg_tree(tmp_path) -> str:
    """pkg/{mod.py, __init__.py, sub/{deep.py, __init__.py}}; return pkg path."""
    d = tmp_path / "pkg"
    sub = d / "sub"
    sub.mkdir(parents=True)
    for p in (d / "mod.py", d / "__init__.py", sub / "deep.py", sub / "__init__.py"):
        p.write_text("x = 1\n")
    return str(d)


# ── directory dispatch: in-process coverage ───────────────────────────────────


@pytest.mark.unit
def test_main_directory_run_mode_exits_1_without_coverage(tmp_path):
    import mutate4py.__main__ as m

    d = tmp_path / "src"
    d.mkdir()
    (d / "a.py").write_text("x = a > b\n")
    sys.argv = ["mutate4py", str(d)]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 1


@pytest.mark.unit
def test_main_directory_check_manifest_missing_exits_1(tmp_path, capsys):
    import mutate4py.__main__ as m

    d = tmp_path / "src"
    d.mkdir()
    (d / "a.py").write_text("def f(): pass\n")
    sys.argv = ["mutate4py", str(d), "--check-manifest"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 1
    assert "Manifest missing:" in capsys.readouterr().out


@pytest.mark.unit
def test_main_directory_check_manifest_current_exits_0(tmp_path, capsys):
    import mutate4py.__main__ as m

    d = tmp_path / "src"
    d.mkdir()
    p = d / "a.py"
    p.write_text("def f(): pass\n")
    sys.argv = ["mutate4py", str(p), "--update-manifest"]
    with pytest.raises(SystemExit):
        m.main()
    capsys.readouterr()

    sys.argv = ["mutate4py", str(d), "--check-manifest"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 0
    assert "Manifest current:" in capsys.readouterr().out


@pytest.mark.unit
def test_main_directory_update_manifest_exits_0(tmp_path, capsys):
    import mutate4py.__main__ as m

    d = tmp_path / "src"
    d.mkdir()
    (d / "a.py").write_text("def f(): pass\n")
    sys.argv = ["mutate4py", str(d), "--update-manifest"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 0
    assert "mutate4py-manifest-begin" in (d / "a.py").read_text()


@pytest.mark.unit
def test_main_directory_scan_exits_0(tmp_path, capsys):
    import mutate4py.__main__ as m

    d = tmp_path / "src"
    d.mkdir()
    (d / "a.py").write_text("x = a > b\n")
    sys.argv = ["mutate4py", str(d), "--scan"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 0
    assert "Mutation scan:" in capsys.readouterr().out


# ── unparseable file in a directory batch (issue #35) ──────────────────────────


@pytest.mark.unit
def test_main_directory_scan_continues_past_syntax_error(tmp_path, capsys):
    """Reproduction from issue #35: good.py / bad.py / zlast.py, bad.py has
    invalid syntax. Every other file must still be scanned; the batch reports
    exit 2 and a trailing parse-failure count, not a traceback."""
    import mutate4py.__main__ as m

    d = tmp_path / "src"
    d.mkdir()
    (d / "good.py").write_text("x = a > b\n")
    (d / "bad.py").write_text("def broken(:\n    pass\n")
    (d / "zlast.py").write_text("y = c > d\n")
    sys.argv = ["mutate4py", str(d), "--scan"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 2
    captured = capsys.readouterr()
    out, err = captured.out, captured.err
    assert f"Mutation scan: {d / 'good.py'}" in out
    assert f"Mutation scan: {d / 'zlast.py'}" in out
    assert f"error: cannot parse {d / 'bad.py'}:" in err
    assert "error: 1 files could not be parsed" in err
    assert "Traceback" not in err


@pytest.mark.component
def test_main_directory_run_mode_continues_past_syntax_error(tmp_path, capsys):
    """The default mutation Run loop (no --scan/--update-manifest/--check-manifest)
    must apply the same continue-the-batch contract as the other three modes
    (issue #35 acceptance: "Applies to ... the Run loop")."""
    import mutate4py.__main__ as m

    d = tmp_path / "src"
    d.mkdir()
    good = d / "good.py"
    bad = d / "bad.py"
    zlast = d / "zlast.py"
    good.write_text("def f(a, b):\n    return a > b\n")
    bad.write_text("def broken(:\n    pass\n")
    zlast.write_text("def g(c, d):\n    return c > d\n")

    lcov = tmp_path / "lcov.info"
    lcov.write_text(f"SF:{good}\nDA:2,1\nend_of_record\nSF:{zlast}\nDA:2,1\nend_of_record\n")

    sys.argv = [
        "mutate4py",
        str(d),
        "--lcov",
        str(lcov),
        "--pytest-args",
        "--collect-only -q tests/test_cmd.py",
        "--no-fork",
    ]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 2
    captured = capsys.readouterr()
    out, err = captured.out, captured.err
    assert f"Mutation run: {good}" in out
    assert f"Mutation run: {zlast}" in out
    assert f"error: cannot parse {bad}:" in err
    assert "error: 1 files could not be parsed" in err
    assert "Traceback" not in err


@pytest.mark.unit
def test_main_directory_update_manifest_continues_past_syntax_error(tmp_path, capsys):
    import mutate4py.__main__ as m

    d = tmp_path / "src"
    d.mkdir()
    (d / "good.py").write_text("x = a > b\n")
    (d / "bad.py").write_text("def broken(:\n    pass\n")
    (d / "zlast.py").write_text("y = c > d\n")
    sys.argv = ["mutate4py", str(d), "--update-manifest"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "mutate4py-manifest-begin" in (d / "good.py").read_text()
    assert "mutate4py-manifest-begin" in (d / "zlast.py").read_text()
    assert (d / "bad.py").read_text() == "def broken(:\n    pass\n"
    assert f"error: cannot parse {d / 'bad.py'}:" in err
    assert "error: 1 files could not be parsed" in err
    assert "Traceback" not in err


@pytest.mark.unit
def test_main_directory_check_manifest_continues_past_syntax_error(tmp_path, capsys):
    """The manifest-exists case from issue #35: bad.py already has a manifest
    footer embedded, but its body was hand-edited into invalid syntax — this is
    the case that actually triggers ast.parse (a file with no manifest at all
    short-circuits check_manifest before ever parsing)."""
    import mutate4py.__main__ as m

    d = tmp_path / "src"
    d.mkdir()
    (d / "good.py").write_text("def f(): pass\n")
    (d / "zlast.py").write_text("def g(): pass\n")
    bad = d / "bad.py"
    bad.write_text("def f(): pass\n")
    sys.argv = ["mutate4py", str(bad), "--update-manifest"]
    with pytest.raises(SystemExit):
        m.main()
    capsys.readouterr()
    bad.write_text(bad.read_text().replace("def f(): pass\n", "def f(:\n    pass\n", 1))

    sys.argv = ["mutate4py", str(d), "--check-manifest"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 2
    captured = capsys.readouterr()
    out, err = captured.out, captured.err
    assert f"Manifest missing: {d / 'good.py'}" in out
    assert f"Manifest missing: {d / 'zlast.py'}" in out
    assert f"error: cannot parse {bad}:" in err
    assert "error: 1 files could not be parsed" in err
    assert "Traceback" not in err


@pytest.mark.unit
def test_main_single_file_syntax_error_exits_nonzero_no_traceback(tmp_path, capsys):
    """A single-file target with invalid syntax exits non-zero with the same
    message and no traceback (issue #35 acceptance)."""
    import mutate4py.__main__ as m

    p = tmp_path / "bad.py"
    p.write_text("def broken(:\n    pass\n")
    sys.argv = ["mutate4py", str(p), "--scan"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert f"error: cannot parse {p}:" in err
    assert "Traceback" not in err


@pytest.mark.unit
def test_main_two_positionals_dispatches_the_union_path_in_process(tmp_path, capsys):
    """Direct (non-subprocess) exercise of the arity>=2 branch through main(),
    so _dispatch/_dispatch_batch/_collect_union_files get real coverage."""
    import mutate4py.__main__ as m

    a_dir = tmp_path / "a_pkg"
    b_dir = tmp_path / "b_pkg"
    a_dir.mkdir()
    b_dir.mkdir()
    (a_dir / "a.py").write_text("def f(): pass\n")
    (b_dir / "b.py").write_text("def g(): pass\n")
    sys.argv = ["mutate4py", str(a_dir), str(b_dir), "--check-manifest"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert f"Manifest missing: {a_dir / 'a.py'}" in out
    assert f"Manifest missing: {b_dir / 'b.py'}" in out


@pytest.mark.unit
def test_main_union_batch_continues_past_syntax_error_in_one_root(tmp_path, capsys):
    """A union batch (two or more resolved roots) must apply the same
    continue-the-batch/worst-code contract as a single directory (issue #35)."""
    import mutate4py.__main__ as m

    a_dir = tmp_path / "a_pkg"
    b_dir = tmp_path / "b_pkg"
    a_dir.mkdir()
    b_dir.mkdir()
    (a_dir / "a.py").write_text("def f(): pass\n")
    bad = a_dir / "bad.py"
    bad.write_text("def h(): pass\n")
    (b_dir / "b.py").write_text("def g(): pass\n")
    sys.argv = ["mutate4py", str(bad), "--update-manifest"]
    with pytest.raises(SystemExit):
        m.main()
    capsys.readouterr()
    # a manifest already exists on bad.py; the body is then hand-corrupted so
    # check_manifest actually reaches ast.parse (issue #35: a file with no
    # manifest at all short-circuits before ever parsing).
    bad.write_text(bad.read_text().replace("def h(): pass\n", "def h(:\n    pass\n", 1))

    sys.argv = ["mutate4py", str(a_dir), str(b_dir), "--check-manifest"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 2
    captured = capsys.readouterr()
    out, err = captured.out, captured.err
    assert f"Manifest missing: {a_dir / 'a.py'}" in out
    assert f"Manifest missing: {b_dir / 'b.py'}" in out
    assert f"error: cannot parse {bad}:" in err
    assert "error: 1 files could not be parsed" in err
    assert "Traceback" not in err


@pytest.mark.unit
def test_main_zero_positionals_dispatches_autodiscovery_in_process(tmp_path, capsys, monkeypatch):
    """Direct (non-subprocess) exercise of the zero-positional branch
    through main(), so _resolve_roots' autodiscovery path gets real
    coverage (mirrors the union-path test above)."""
    import mutate4py.__main__ as m

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "pyproject.toml").write_text("[tool.uv.workspace]\n")
    (ws / "a.py").write_text("def f(): pass\n")
    monkeypatch.chdir(ws)
    sys.argv = ["mutate4py", "--check-manifest"]
    with pytest.raises(SystemExit) as exc:
        m.main()
    assert exc.value.code == 1
    assert f"Manifest missing: {ws / 'a.py'}" in capsys.readouterr().out


# ── multi-root positionals (issue #22): CLI-level arity/union behavior ─────────


@pytest.mark.integration
def test_union_two_directories_processes_files_from_both(tmp_path):
    a_dir = tmp_path / "a_pkg"
    b_dir = tmp_path / "b_pkg"
    a_dir.mkdir()
    b_dir.mkdir()
    (a_dir / "a.py").write_text("def f(): pass\n")
    (b_dir / "b.py").write_text("def g(): pass\n")
    result = _run_cli_path(str(a_dir), str(b_dir), "--check-manifest")
    assert result.returncode == 1
    assert f"Manifest missing: {a_dir / 'a.py'}" in result.stdout
    assert f"Manifest missing: {b_dir / 'b.py'}" in result.stdout


@pytest.mark.integration
def test_union_glob_pattern_matching_two_files_processes_both(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "a.py").write_text("def f(): pass\n")
    (d / "b.py").write_text("def g(): pass\n")
    result = _run_cli_path(str(d / "*.py"), "--check-manifest")
    assert result.returncode == 1
    assert f"Manifest missing: {d / 'a.py'}" in result.stdout
    assert f"Manifest missing: {d / 'b.py'}" in result.stdout


@pytest.mark.integration
def test_single_glob_match_dispatches_as_a_single_file(tmp_path):
    """Arity rule (item 2): exactly one resolved path -> today's single-file
    dispatch, even though the argument was a glob pattern."""
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "only.py").write_text("def f(): pass\n")
    result = _run_cli_path(str(d / "*.py"), "--check-manifest")
    assert result.returncode == 1
    assert f"Manifest missing: {d / 'only.py'}" in result.stdout


@pytest.mark.integration
def test_glob_matched_non_py_file_is_dropped_silently(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "a.py").write_text("def f(): pass\n")
    (d / "README.md").write_text("docs\n")
    result = _run_cli_path(str(d / "*"), "--check-manifest")
    assert result.returncode == 1
    assert "README.md" not in result.stdout
    assert f"Manifest missing: {d / 'a.py'}" in result.stdout


@pytest.mark.integration
def test_literal_non_py_single_target_still_uses_todays_dispatch(tmp_path):
    """Item 6's carve-out: a literally-typed (non-wildcard) path is never
    silently dropped for lacking a .py suffix; arity 1 always reaches the
    unchanged single-file dispatch, whatever it does with the content."""
    p = tmp_path / "README.md"
    p.write_text("x = 1\n")
    result = _run_cli_path(str(p), "--check-manifest")
    assert result.returncode == 1
    assert f"Manifest missing: {p}" in result.stdout


@pytest.mark.integration
def test_pattern_matching_nothing_exits_2_naming_the_pattern(tmp_path):
    pattern = str(tmp_path / "nosuch" / "*.py")
    result = _run_cli_path(pattern, "--check-manifest")
    assert result.returncode == 2
    assert pattern in result.stderr


@pytest.mark.integration
def test_union_fails_fast_before_processing_any_file(tmp_path):
    """Item 7: all positionals are validated before anything is collected —
    a bad second pattern must produce no output for the good first one."""
    a_dir = tmp_path / "a_pkg"
    a_dir.mkdir()
    (a_dir / "a.py").write_text("def f(): pass\n")
    missing = str(tmp_path / "no_such_file.py")
    result = _run_cli_path(str(a_dir), missing, "--check-manifest")
    assert result.returncode == 2
    assert result.stdout == ""
    assert missing in result.stderr


@pytest.mark.integration
def test_union_dedups_the_same_root_given_twice(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "a.py").write_text("def f(): pass\n")
    result = _run_cli_path(str(d), str(d), "--check-manifest")
    assert result.returncode == 1
    assert result.stdout.count("a.py") == 1


@pytest.mark.integration
def test_union_preserves_root_order_not_a_global_sort(tmp_path):
    """Item 15: files from the first root's walk print before the second
    root's, even though the second root's filename would sort first."""
    z_dir = tmp_path / "z_pkg"
    a_dir = tmp_path / "a_pkg"
    z_dir.mkdir()
    a_dir.mkdir()
    (z_dir / "zz.py").write_text("def f(): pass\n")
    (a_dir / "aa.py").write_text("def g(): pass\n")
    result = _run_cli_path(str(z_dir), str(a_dir), "--check-manifest")
    assert result.stdout.index("zz.py") < result.stdout.index("aa.py")


@pytest.mark.integration
def test_union_empty_root_is_silent_when_another_root_has_files(tmp_path):
    """Item 17: an individual empty root is not an error; only an empty
    whole union is."""
    empty_dir = tmp_path / "empty_pkg"
    full_dir = tmp_path / "full_pkg"
    empty_dir.mkdir()
    full_dir.mkdir()
    (full_dir / "a.py").write_text("def f(): pass\n")
    result = _run_cli_path(str(empty_dir), str(full_dir), "--check-manifest")
    assert result.returncode == 1
    assert "no Python files to process" not in result.stderr


@pytest.mark.integration
def test_union_whole_union_empty_exits_2(tmp_path):
    empty_a = tmp_path / "empty_a"
    empty_b = tmp_path / "empty_b"
    empty_a.mkdir()
    empty_b.mkdir()
    result = _run_cli_path(str(empty_a), str(empty_b), "--check-manifest")
    assert result.returncode == 2
    assert "error: no Python files to process." in result.stderr


@pytest.mark.integration
def test_union_exclude_composes_with_multiple_roots(tmp_path):
    a_dir = tmp_path / "a_pkg"
    b_dir = tmp_path / "b_pkg"
    a_dir.mkdir()
    b_dir.mkdir()
    (a_dir / "a.py").write_text("def f(): pass\n")
    (b_dir / "b.py").write_text("def g(): pass\n")
    result = _run_cli_path(str(a_dir), str(b_dir), "--check-manifest", "--exclude", "**/b.py")
    assert result.returncode == 1
    assert f"Manifest missing: {a_dir / 'a.py'}" in result.stdout
    assert "b.py" not in result.stdout


@pytest.mark.integration
def test_zero_positionals_triggers_autodiscovery(tmp_path):
    """Issue #22 item 3: no new flag, the absence of positionals is the
    autodiscovery trigger. This repo's own pyproject.toml has no
    [tool.uv.workspace], so autodiscovery from REPO_ROOT errors there —
    which is itself proof that autodiscovery ran, not the old "missing
    positional" usage error."""
    result = subprocess.run(
        [sys.executable, "-m", "mutate4py", "--scan"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": os.path.join(REPO_ROOT, "src")},
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert os.path.join(REPO_ROOT, "pyproject.toml") in result.stderr
    assert "[tool.uv.workspace]" in result.stderr


# ── uv workspace autodiscovery (issue #22 items 3, 8-12): CLI-level ────────────


def _write_workspace(tmp_path, members=None, exclude=None):
    """Build a workspace at tmp_path/"ws"; return its path."""
    ws = tmp_path / "ws"
    ws.mkdir()
    lines = ["[tool.uv.workspace]"]
    if members is not None:
        items = ", ".join(f'"{m}"' for m in members)
        lines.append(f"members = [{items}]")
    if exclude is not None:
        items = ", ".join(f'"{e}"' for e in exclude)
        lines.append(f"exclude = [{items}]")
    (ws / "pyproject.toml").write_text("\n".join(lines) + "\n")
    return ws


@pytest.mark.integration
def test_autodiscovery_single_root_workspace_check_manifest(tmp_path):
    ws = _write_workspace(tmp_path)
    (ws / "a.py").write_text("def f(): pass\n")
    result = _run_cli_in(str(ws), "--check-manifest")
    assert result.returncode == 1
    assert f"Manifest missing: {ws / 'a.py'}" in result.stdout


@pytest.mark.integration
def test_autodiscovery_multi_member_workspace_unions_all_roots(tmp_path):
    ws = _write_workspace(tmp_path, members=["pkgs/*"])
    a_dir, b_dir = ws / "pkgs" / "a", ws / "pkgs" / "b"
    a_dir.mkdir(parents=True)
    b_dir.mkdir(parents=True)
    (a_dir / "pyproject.toml").write_text('[project]\nname = "a"\n')
    (b_dir / "pyproject.toml").write_text('[project]\nname = "b"\n')
    (a_dir / "a.py").write_text("def f(): pass\n")
    (b_dir / "b.py").write_text("def g(): pass\n")
    result = _run_cli_in(str(ws), "--check-manifest")
    assert result.returncode == 1
    assert f"Manifest missing: {a_dir / 'a.py'}" in result.stdout
    assert f"Manifest missing: {b_dir / 'b.py'}" in result.stdout


@pytest.mark.integration
def test_autodiscovery_exclude_removes_member_files_from_the_union(tmp_path):
    """Item 10: an excluded member's files are absent from the union even
    though they physically sit under the workspace root's recursive walk."""
    ws = _write_workspace(tmp_path, members=["pkgs/*"], exclude=["pkgs/b"])
    a_dir, b_dir = ws / "pkgs" / "a", ws / "pkgs" / "b"
    a_dir.mkdir(parents=True)
    b_dir.mkdir(parents=True)
    (a_dir / "pyproject.toml").write_text('[project]\nname = "a"\n')
    (b_dir / "pyproject.toml").write_text('[project]\nname = "b"\n')
    (a_dir / "a.py").write_text("def f(): pass\n")
    (b_dir / "b.py").write_text("def g(): pass\n")
    result = _run_cli_in(str(ws), "--check-manifest")
    assert result.returncode == 1
    assert f"Manifest missing: {a_dir / 'a.py'}" in result.stdout
    assert "b.py" not in result.stdout


@pytest.mark.integration
def test_autodiscovery_no_workspace_found_exits_2(tmp_path):
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    result = _run_cli_in(str(isolated), "--scan")
    assert result.returncode == 2
    assert result.stdout == ""
    assert "pyproject.toml" in result.stderr
    assert str(isolated) in result.stderr


@pytest.mark.integration
def test_autodiscovery_help_mentions_it(tmp_path):
    result = _run_cli_in(str(tmp_path), "--help")
    assert result.returncode == 0
    assert "autodiscov" in result.stdout.lower()
