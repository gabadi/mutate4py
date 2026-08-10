"""Unit tests for F4 run loop (_runner.py)."""

import os

import pytest

from ._pytest_project_helpers import (
    write_always_failing_pytest_project,
    write_always_passing_pytest_project,
    write_content_check_pytest_project,
    write_sleep_if_mutated_pytest_project,
)
from mutate4py._discovery import discover_sites
from mutate4py._manifest import build_manifest, embed_manifest
from mutate4py._runner import (
    CoverageSource,
    RunMutationsRequest,
    _baseline_reason,
    check_manifest,
    run_mutations,
    run_scan,
    update_manifest,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# ── run_mutations integration ─────────────────────────────────────────────────


def _write_lcov(path: str, source_abs: str, covered_lines: list[int]) -> None:
    da_lines = "\n".join(f"DA:{ln},1" for ln in covered_lines)
    content = f"SF:{source_abs}\n{da_lines}\nend_of_record\n"
    with open(path, "w") as f:
        f.write(content)


def test_run_mutations_killed_mutant(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    sites = discover_sites(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov(lcov_path, src_path, [s.line for s in sites])

    pytest_args = write_content_check_pytest_project(str(tmp_path), src_path, sites[0].mutant_text)

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                cov_cmd=None,
                lcov_path=lcov_path,
                reuse_coverage=False,
                pytest_args=pytest_args,
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                cwd=str(tmp_path),
            )
        )
    output = buf.getvalue()
    assert rc == 0
    assert "killed" in output
    assert "Killed: 1" in output
    assert "Survived: 0" in output


def test_run_mutations_survived_mutant(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    sites = discover_sites(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov(lcov_path, src_path, [s.line for s in sites])

    pytest_args = write_always_passing_pytest_project(str(tmp_path))

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                cov_cmd=None,
                lcov_path=lcov_path,
                reuse_coverage=False,
                pytest_args=pytest_args,
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                cwd=str(tmp_path),
            )
        )
    output = buf.getvalue()
    n_sites = len(sites)
    assert rc == 0
    assert "survived" in output
    assert "Survived: 1" in output
    assert "Survivors:" in output
    assert f"[1/{n_sites}]" in output


def test_run_mutations_sidecar_writes_manifest_file_and_footer_free_source(tmp_path):
    import json

    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    sites = discover_sites(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov(lcov_path, src_path, [s.line for s in sites])

    pytest_args = write_always_passing_pytest_project(str(tmp_path))

    sidecar_path = src_path + ".manifest.json"

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                cov_cmd=None,
                lcov_path=lcov_path,
                reuse_coverage=False,
                pytest_args=pytest_args,
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                cwd=str(tmp_path),
                manifest_file=True,
            )
        )

    assert rc == 0
    with open(src_path) as f:
        final_source = f.read()
    assert final_source == src
    assert "mutate4py-manifest-begin" not in final_source

    with open(sidecar_path) as f:
        sidecar = json.load(f)
    assert sidecar["functions"][0]["id"] == "func/f"


def test_run_mutations_baseline_failure_exits_1(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    sites = discover_sites(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov(lcov_path, src_path, [s.line for s in sites])

    pytest_args = write_always_failing_pytest_project(str(tmp_path))

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                cov_cmd=None,
                lcov_path=lcov_path,
                reuse_coverage=False,
                pytest_args=pytest_args,
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                cwd=str(tmp_path),
            )
        )
    output = buf.getvalue()
    assert rc == 1
    assert "baseline failed:" in output
    assert "Mutation Report" not in output
    # No backup left
    assert not os.path.exists(src_path + ".bak")


def test_baseline_reason_uses_stderr_first():
    import subprocess

    result = subprocess.CompletedProcess(args=[], returncode=1, stderr=b"test suite crashed\nsecond line")
    assert _baseline_reason(result) == "test suite crashed"


def test_baseline_reason_falls_back_to_exit_code():
    import subprocess

    result = subprocess.CompletedProcess(args=[], returncode=42, stderr=b"")
    assert _baseline_reason(result) == "exit code 42"


def test_run_mutations_restores_source_after_run(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    sites = discover_sites(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov(lcov_path, src_path, [s.line for s in sites])

    pytest_args = write_always_passing_pytest_project(str(tmp_path))

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                cov_cmd=None,
                lcov_path=lcov_path,
                reuse_coverage=False,
                pytest_args=pytest_args,
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                cwd=str(tmp_path),
            )
        )

    # Source should have no mutant; bak should be gone
    with open(src_path) as f:
        final = f.read()
    assert sites[0].mutant_text not in final
    assert not os.path.exists(src_path + ".bak")


def test_run_mutations_crash_safety_restores_bak(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    bak_path = src_path + ".bak"

    # Simulate interrupted run: bak has clean source, src has a mutant spliced in
    with open(bak_path, "w") as f:
        f.write(src)
    with open(src_path, "w") as f:
        f.write("def f(a, b):\n    return a >= b\n")  # mutant left in

    sites = discover_sites(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov(lcov_path, src_path, [s.line for s in sites])

    pytest_args = write_always_passing_pytest_project(str(tmp_path))

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                cov_cmd=None,
                lcov_path=lcov_path,
                reuse_coverage=False,
                pytest_args=pytest_args,
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                cwd=str(tmp_path),
            )
        )
    output = buf.getvalue()
    assert "Restored source from backup" in output


def test_run_mutations_preserves_tested_at_when_manifest_already_current(tmp_path):
    """A scored --mutate-all run against source whose embedded manifest already
    matches (module/function hashes unchanged) retains the OLD tested_at instead
    of bumping it to now — i.e. the second of two runs on unchanged source produces
    no diff. Uses a deliberately old tested_at so the assertion can't pass by luck
    if both runs happen to land within the same wall-clock second."""
    import json

    from mutate4py._manifest import build_manifest, embed_manifest

    src = "def f(a, b):\n    return a > b\n"
    old_tested_at = "2020-01-01T00:00:00Z"
    manifest = build_manifest(src, tested_at=old_tested_at)
    source_with_manifest = embed_manifest(src, manifest)

    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(source_with_manifest)

    sites = discover_sites(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov(lcov_path, src_path, [s.line for s in sites])

    pytest_args = write_always_passing_pytest_project(str(tmp_path))

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=source_with_manifest,
                cov_cmd=None,
                lcov_path=lcov_path,
                reuse_coverage=False,
                pytest_args=pytest_args,
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=True,
                warning_threshold=1000,
                cwd=str(tmp_path),
            )
        )

    with open(src_path) as f:
        content = f.read()
    manifest_line = [ln for ln in content.splitlines() if ln.startswith("# {")][0]
    result_manifest = json.loads(manifest_line[2:])
    assert result_manifest["tested_at"] == old_tested_at
    assert content == source_with_manifest


def test_run_mutations_reuse_coverage_warns(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    sites = discover_sites(src)
    # Write to the default coverage.lcov path
    lcov_path = str(tmp_path / "coverage.lcov")
    _write_lcov(lcov_path, src_path, [s.line for s in sites])

    pytest_args = write_always_passing_pytest_project(str(tmp_path))

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                cov_cmd=None,
                lcov_path=None,
                reuse_coverage=True,
                pytest_args=pytest_args,
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                cwd=str(tmp_path),
            )
        )
    output = buf.getvalue()
    assert "Reusing existing coverage" in output
    # Warning must appear before the header
    warn_pos = output.index("Reusing existing coverage")
    header_pos = output.index("Mutation run:")
    assert warn_pos < header_pos


def test_run_mutations_header_counts(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    sites = discover_sites(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov(lcov_path, src_path, [s.line for s in sites])

    pytest_args = write_always_passing_pytest_project(str(tmp_path))

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                cov_cmd=None,
                lcov_path=lcov_path,
                reuse_coverage=False,
                pytest_args=pytest_args,
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                cwd=str(tmp_path),
            )
        )
    output = buf.getvalue()
    assert "Mutation run:" in output
    assert "Total mutation sites:" in output
    assert "Covered mutation sites:" in output
    assert "Uncovered mutation sites:" in output
    assert "Changed mutation sites:" in output
    assert "Manifest exists:" in output
    assert "Selected mutation sites:" in output
    assert "Mutation workers:" not in output


def test_run_mutations_prints_uncovered_block_for_uncovered_sites(tmp_path):
    """Pins the exact "Uncovered mutations:" block text through run_mutations —
    gate 14 turned its production (_uncovered_lines_if_needed) from a print into
    a return, and _select_and_prepare's _print_lines(...) wrapping must still
    produce byte-for-byte the same output as before that change.
    """
    src = "def f(a, b):\n    return a > b\n\n\ndef g(a, b):\n    return a < b\n"
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    sites = discover_sites(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov(lcov_path, src_path, [sites[0].line])  # only the first site is covered

    pytest_args = write_always_passing_pytest_project(str(tmp_path))

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                cov_cmd=None,
                lcov_path=lcov_path,
                reuse_coverage=False,
                pytest_args=pytest_args,
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                cwd=str(tmp_path),
            )
        )
    output = buf.getvalue()
    assert "Uncovered mutations:" in output
    assert f"  line {sites[1].line} {sites[1].desc} {sites[1].function_id}" in output


def test_run_mutations_timeout_counts_as_killed(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    sites = discover_sites(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov(lcov_path, src_path, [s.line for s in sites])

    # Baseline passes quickly, mutant sleeps past the short timeout
    pytest_args = write_sleep_if_mutated_pytest_project(str(tmp_path), src_path, sites[0].mutant_text, 5)

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                cov_cmd=None,
                lcov_path=lcov_path,
                reuse_coverage=False,
                pytest_args=pytest_args,
                timeout_factor=1,
                min_timeout=0.1,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                cwd=str(tmp_path),
            )
        )
    output = buf.getvalue()
    assert "timeout" in output
    assert "Killed: 1" in output  # timeout counts as killed
    assert "Survived: 0" in output


# ── check_manifest ────────────────────────────────────────────────────────────


def _source_with_current_manifest(tmp_path, src: str) -> tuple[str, str]:
    """Write src to a temp file, embed a manifest, return (path, source_with_manifest)."""
    p = tmp_path / "mod.py"
    p.write_text(src)
    update_manifest(path=str(p), source=src)
    return str(p), p.read_text()


def test_check_manifest_missing_returns_1(tmp_path, capsys):
    src = "def f(a, b):\n    return a > b\n"
    p = tmp_path / "mod.py"
    p.write_text(src)
    rc = check_manifest(path=str(p), source=src)
    assert rc == 1


def test_check_manifest_missing_prints_message(tmp_path, capsys):
    src = "def f(a, b):\n    return a > b\n"
    p = tmp_path / "mod.py"
    p.write_text(src)
    check_manifest(path=str(p), source=src)
    assert "Manifest missing:" in capsys.readouterr().out


def test_check_manifest_current_returns_0(tmp_path, capsys):
    src = "def f(a, b):\n    return a > b\n"
    path, source_with_manifest = _source_with_current_manifest(tmp_path, src)
    capsys.readouterr()
    rc = check_manifest(path=path, source=source_with_manifest)
    assert rc == 0


def test_check_manifest_current_prints_message(tmp_path, capsys):
    src = "def f(a, b):\n    return a > b\n"
    path, source_with_manifest = _source_with_current_manifest(tmp_path, src)
    capsys.readouterr()
    check_manifest(path=path, source=source_with_manifest)
    assert "Manifest current:" in capsys.readouterr().out


def test_check_manifest_stale_returns_1(tmp_path, capsys):
    src = "def f(a, b):\n    return a > b\n"
    path, source_with_manifest = _source_with_current_manifest(tmp_path, src)
    capsys.readouterr()
    stale_source = source_with_manifest.replace("a > b", "a + b")
    rc = check_manifest(path=path, source=stale_source)
    assert rc == 1


def test_check_manifest_stale_prints_message(tmp_path, capsys):
    src = "def f(a, b):\n    return a > b\n"
    path, source_with_manifest = _source_with_current_manifest(tmp_path, src)
    capsys.readouterr()
    stale_source = source_with_manifest.replace("a > b", "a + b")
    check_manifest(path=path, source=stale_source)
    assert "Manifest stale:" in capsys.readouterr().out


def test_check_manifest_does_not_modify_file(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    p = tmp_path / "mod.py"
    p.write_text(src)
    before = p.read_text()
    check_manifest(path=str(p), source=src)
    assert p.read_text() == before


# ── check_manifest: fast path (source_sha256) ─────────────────────────────────


def test_check_manifest_fast_path_does_not_parse(tmp_path, monkeypatch):
    """Matching source_sha256 must short-circuit before any AST parse."""
    import ast

    src = "def f(a, b):\n    return a > b\n"
    path, source_with_manifest = _source_with_current_manifest(tmp_path, src)

    def _forbidden_parse(*args, **kwargs):
        raise AssertionError("ast.parse must not run on the check_manifest fast path")

    monkeypatch.setattr(ast, "parse", _forbidden_parse)

    rc = check_manifest(path=path, source=source_with_manifest)
    assert rc == 0


def test_check_manifest_fast_path_current_returns_0(tmp_path, capsys):
    src = "def f(a, b):\n    return a > b\n"
    path, source_with_manifest = _source_with_current_manifest(tmp_path, src)
    capsys.readouterr()

    rc = check_manifest(path=path, source=source_with_manifest)

    assert rc == 0
    assert f"Manifest current: {path}" in capsys.readouterr().out


def test_check_manifest_missing_source_sha256_falls_back_to_slow_path(tmp_path, capsys):
    """A manifest without source_sha256 (pre-existing, additive) still works via
    the full parse-and-compare path."""
    src = "def f(a, b):\n    return a > b\n"
    p = tmp_path / "mod.py"
    p.write_text(src)
    manifest = build_manifest(src, tested_at="2020-01-01T00:00:00Z")
    del manifest["source_sha256"]
    p.write_text(embed_manifest(src, manifest))
    source_with_manifest = p.read_text()

    rc = check_manifest(path=str(p), source=source_with_manifest)

    assert rc == 0
    assert "Manifest current:" in capsys.readouterr().out


def test_check_manifest_comment_only_edit_still_current_via_slow_path(tmp_path, capsys):
    """A byte-level source_sha256 mismatch (comment-only edit) must fall through
    to the structural (AST) comparison rather than reporting stale."""
    src = "def f(a, b):\n    return a > b\n"
    path, source_with_manifest = _source_with_current_manifest(tmp_path, src)
    capsys.readouterr()
    commented_source = source_with_manifest.replace("def f(a, b):", "def f(a, b):\n    # a comment")

    rc = check_manifest(path=path, source=commented_source)

    assert rc == 0
    assert "Manifest current:" in capsys.readouterr().out


# ── unparseable source propagates SyntaxError (issue #35) ─────────────────────
#
# check_manifest/update_manifest/run_scan/run_mutations must let a SyntaxError
# from ast.parse propagate uncaught — the CLI's per-file dispatch (__main__.py)
# is the layer responsible for catching it and keeping the batch going.


def test_check_manifest_propagates_syntax_error_when_body_corrupted(tmp_path):
    """A manifest exists but the body underneath is unparseable (e.g. hand-edited
    after embedding) — this is the exact case that hid the bug (issue #35): with
    no manifest at all, check_manifest short-circuits before ever parsing."""
    src = "def f(a, b):\n    return a > b\n"
    path, source_with_manifest = _source_with_current_manifest(tmp_path, src)
    broken_source = source_with_manifest.replace("def f(a, b):\n    return a > b\n", "def f(a, b:\n    return a > b\n")
    with pytest.raises(SyntaxError):
        check_manifest(path=path, source=broken_source)


def test_update_manifest_propagates_syntax_error(tmp_path):
    p = tmp_path / "mod.py"
    src = "def f(a, b:\n    return a > b\n"
    p.write_text(src)
    with pytest.raises(SyntaxError):
        update_manifest(path=str(p), source=src)


def test_run_scan_propagates_syntax_error(tmp_path):
    p = tmp_path / "mod.py"
    src = "def f(a, b:\n    return a > b\n"
    p.write_text(src)
    with pytest.raises(SyntaxError):
        run_scan(
            path=str(p),
            source=src,
            warning_threshold=50,
            coverage=CoverageSource(cov_cmd=None, lcov_path=None, reuse_coverage=False, cwd=str(tmp_path)),
        )


def test_run_mutations_propagates_syntax_error(tmp_path):
    src = "def broken(:\n    pass\n"
    src_path = str(tmp_path / "bad.py")
    with open(src_path, "w") as f:
        f.write(src)

    with pytest.raises(SyntaxError):
        run_mutations(
            RunMutationsRequest(
                path=src_path,
                source=src,
                cov_cmd=None,
                lcov_path=None,
                reuse_coverage=False,
                pytest_args=[],
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                cwd=str(tmp_path),
            )
        )


# ── update_manifest / check_manifest: sidecar mode (--manifest-file) ──────────


def test_update_manifest_sidecar_writes_manifest_file(tmp_path):
    import json

    src = "def f(a, b):\n    return a > b\n"
    p = tmp_path / "mod.py"
    p.write_text(src)
    sidecar = tmp_path / "mod.py.manifest.json"

    update_manifest(path=str(p), source=src, manifest_file=True)

    assert sidecar.is_file()
    sidecar_data = json.loads(sidecar.read_text())
    assert sidecar_data["version"] == 1
    assert sidecar_data["functions"][0]["id"] == "func/f"


def test_update_manifest_sidecar_overwrites_corrupted_sidecar(tmp_path):
    """A hand-corrupted sidecar (valid JSON, not a manifest object) reads as
    missing and gets replaced by --update-manifest, not left in place."""
    import json

    src = "def f(a, b):\n    return a > b\n"
    p = tmp_path / "mod.py"
    p.write_text(src)
    sidecar = tmp_path / "mod.py.manifest.json"
    sidecar.write_text("[1, 2, 3]")

    update_manifest(path=str(p), source=src, manifest_file=True)

    sidecar_data = json.loads(sidecar.read_text())
    assert sidecar_data["functions"][0]["id"] == "func/f"


def test_update_manifest_sidecar_does_not_touch_other_files_sidecars(tmp_path):
    """Each file's sidecar lives at its own <file>.manifest.json, so a directory
    run updating one file must not affect another file's sidecar or source."""
    src_a = "def f(a, b):\n    return a > b\n"
    src_b = "def g(c, d):\n    return c + d\n"
    p_a = tmp_path / "a.py"
    p_b = tmp_path / "b.py"
    p_a.write_text(src_a)
    p_b.write_text(src_b)

    update_manifest(path=str(p_a), source=src_a, manifest_file=True)
    update_manifest(path=str(p_b), source=src_b, manifest_file=True)

    assert p_a.read_text() == src_a
    assert p_b.read_text() == src_b
    assert "mutate4py-manifest-begin" not in p_a.read_text()
    assert "mutate4py-manifest-begin" not in p_b.read_text()

    rc_a = check_manifest(path=str(p_a), source=src_a, manifest_file=True)
    rc_b = check_manifest(path=str(p_b), source=src_b, manifest_file=True)
    assert rc_a == 0
    assert rc_b == 0


def test_update_manifest_sidecar_leaves_source_free_of_footer(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    p = tmp_path / "mod.py"
    p.write_text(src)

    update_manifest(path=str(p), source=src, manifest_file=True)

    assert p.read_text() == src
    assert "mutate4py-manifest-begin" not in p.read_text()


def test_update_manifest_sidecar_reports_updated(tmp_path, capsys):
    src = "def f(a, b):\n    return a > b\n"
    p = tmp_path / "mod.py"
    p.write_text(src)

    update_manifest(path=str(p), source=src, manifest_file=True)

    assert f"Updated manifest: {p}" in capsys.readouterr().out


def test_update_manifest_sidecar_second_run_is_unchanged(tmp_path, capsys):
    src = "def f(a, b):\n    return a > b\n"
    p = tmp_path / "mod.py"
    p.write_text(src)
    sidecar = tmp_path / "mod.py.manifest.json"

    update_manifest(path=str(p), source=src, manifest_file=True)
    sidecar_before = sidecar.read_text()
    source_before = p.read_text()
    capsys.readouterr()

    update_manifest(path=str(p), source=p.read_text(), manifest_file=True)

    assert f"Manifest unchanged: {p}" in capsys.readouterr().out
    assert sidecar.read_text() == sidecar_before
    assert p.read_text() == source_before


def test_update_manifest_sidecar_strips_stale_footer_even_when_sidecar_current(
    tmp_path,
):
    """Migrating embedded->sidecar must strip the old footer even if the sidecar
    already happens to be structurally current (e.g. written by a previous
    --manifest-file run against the same unchanged content)."""
    src = "def f(a, b):\n    return a > b\n"
    p = tmp_path / "mod.py"
    p.write_text(src)

    # Sidecar already current for this content...
    update_manifest(path=str(p), source=src, manifest_file=True)
    # ...but the file on disk somehow still carries a stale embedded footer
    # (e.g. left over from switching a file from embedded to sidecar storage).
    stale_embedded_source = embed_manifest(src, {"version": 1, "tested_at": "x", "module_hash": "old", "functions": []})
    p.write_text(stale_embedded_source)

    update_manifest(path=str(p), source=stale_embedded_source, manifest_file=True)

    assert p.read_text() == src
    assert "mutate4py-manifest-begin" not in p.read_text()


def test_update_manifest_default_mode_unaffected_by_manifest_file_param(tmp_path):
    """manifest_file omitted (default False) => byte-identical to today's embed behavior."""
    src = "def f(a, b):\n    return a > b\n"
    p_default = tmp_path / "default.py"
    p_default.write_text(src)
    p_explicit_false = tmp_path / "explicit_false.py"
    p_explicit_false.write_text(src)

    update_manifest(path=str(p_default), source=src)
    update_manifest(path=str(p_explicit_false), source=src, manifest_file=False)

    assert p_default.read_text() == p_explicit_false.read_text()
    assert "mutate4py-manifest-begin" in p_default.read_text()


def test_check_manifest_sidecar_missing_returns_1(tmp_path, capsys):
    src = "def f(a, b):\n    return a > b\n"
    p = tmp_path / "mod.py"
    p.write_text(src)

    rc = check_manifest(path=str(p), source=src, manifest_file=True)

    assert rc == 1
    assert "Manifest missing:" in capsys.readouterr().out


def test_check_manifest_sidecar_current_returns_0(tmp_path, capsys):
    src = "def f(a, b):\n    return a > b\n"
    p = tmp_path / "mod.py"
    p.write_text(src)
    update_manifest(path=str(p), source=src, manifest_file=True)
    capsys.readouterr()

    rc = check_manifest(path=str(p), source=p.read_text(), manifest_file=True)

    assert rc == 0
    assert "Manifest current:" in capsys.readouterr().out


def test_check_manifest_sidecar_fast_path_does_not_parse(tmp_path, monkeypatch):
    """The source_sha256 fast path applies to sidecar storage too, not just the
    embedded footer — matching bytes must short-circuit before any AST parse."""
    import ast

    src = "def f(a, b):\n    return a > b\n"
    p = tmp_path / "mod.py"
    p.write_text(src)
    update_manifest(path=str(p), source=src, manifest_file=True)

    def _forbidden_parse(*args, **kwargs):
        raise AssertionError("ast.parse must not run on the check_manifest fast path")

    monkeypatch.setattr(ast, "parse", _forbidden_parse)

    rc = check_manifest(path=str(p), source=p.read_text(), manifest_file=True)
    assert rc == 0


def test_check_manifest_sidecar_stale_returns_1(tmp_path, capsys):
    src = "def f(a, b):\n    return a > b\n"
    p = tmp_path / "mod.py"
    p.write_text(src)
    update_manifest(path=str(p), source=src, manifest_file=True)
    capsys.readouterr()
    stale_source = src.replace("a > b", "a + b")

    rc = check_manifest(path=str(p), source=stale_source, manifest_file=True)

    assert rc == 1
    assert "Manifest stale:" in capsys.readouterr().out


def test_check_manifest_sidecar_ignores_embedded_footer_in_source(tmp_path, capsys):
    """A stray in-source footer must not satisfy a sidecar-mode check."""
    src = "def f(a, b):\n    return a > b\n"
    p = tmp_path / "mod.py"
    p.write_text(src)
    update_manifest(path=str(p), source=src)  # embeds a footer, no sidecar written
    embedded_source = p.read_text()

    rc = check_manifest(path=str(p), source=embedded_source, manifest_file=True)

    assert rc == 1
    assert "Manifest missing:" in capsys.readouterr().out
