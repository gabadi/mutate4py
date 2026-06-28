"""Unit tests for F4 run loop (_runner.py)."""

import os


from mutate4py._discovery import Site, apply_mutant, discover_sites
from mutate4py._runner import (
    _baseline_reason,
    _print_uncovered_block,
    _run_command,
    _select_sites,
    run_mutations,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# ── apply_mutant ──────────────────────────────────────────────────────────────


def test_apply_mutant_replaces_operator():
    src = "def f(a, b):\n    return a > b\n"
    sites = discover_sites(src)
    assert len(sites) == 1
    mutated = apply_mutant(src, sites[0])
    assert "a >= b" in mutated
    assert "a > b" not in mutated


def test_apply_mutant_restores_via_orig_text():
    src = "def f(a, b):\n    return a + b\n"
    sites = discover_sites(src)
    mutated = apply_mutant(src, sites[0])
    # Restoring: apply the inverse (orig_text back)
    assert mutated != src
    assert sites[0].orig_text in src
    assert sites[0].mutant_text in mutated


def test_apply_mutant_constant_true_to_false():
    src = "x = True\n"
    sites = discover_sites(src)
    assert len(sites) == 1
    mutated = apply_mutant(src, sites[0])
    assert mutated.strip() == "x = False"


def test_apply_mutant_integer_0_to_1():
    src = "x = 0\n"
    sites = discover_sites(src)
    mutated = apply_mutant(src, sites[0])
    assert mutated.strip() == "x = 1"


# ── _run_command ──────────────────────────────────────────────────────────────


def test_run_command_exit_zero_is_survived():
    status, timed_out = _run_command("exit 0", "/tmp", timeout=5.0)
    assert status == "survived"
    assert not timed_out


def test_run_command_exit_nonzero_is_killed():
    status, timed_out = _run_command("exit 1", "/tmp", timeout=5.0)
    assert status == "killed"
    assert not timed_out


def test_run_command_timeout_is_timeout():
    status, timed_out = _run_command("sleep 10", "/tmp", timeout=0.1)
    assert status == "timeout"
    assert timed_out


# ── _select_sites ─────────────────────────────────────────────────────────────


def _make_site(index, line, fid="func/f") -> Site:
    return Site(
        index=index,
        line=line,
        col=0,
        end_line=line,
        end_col=5,
        function_id=fid,
        orig_text=">",
        mutant_text=">=",
        desc="> -> >=",
    )


def test_select_sites_all_covered_non_differential():
    sites = [_make_site(0, 1, "func/f"), _make_site(1, 2, "func/g")]
    covered = {1, 2}
    _, selected = _select_sites(sites, covered, set(), False, None)
    assert len(selected) == 2


def test_select_sites_differential_filters_unchanged():
    sites = [_make_site(0, 1, "func/f"), _make_site(1, 2, "func/g")]
    covered = {1, 2}
    changed = {"func/f"}
    _, selected = _select_sites(sites, covered, changed, True, None)
    assert len(selected) == 1
    assert selected[0].function_id == "func/f"


def test_select_sites_lines_filter():
    sites = [_make_site(0, 1, "func/f"), _make_site(1, 2, "func/g")]
    covered = {1, 2}
    _, selected = _select_sites(sites, covered, set(), False, {1})
    assert len(selected) == 1
    assert selected[0].line == 1


def test_select_sites_uncovered_excluded():
    sites = [_make_site(0, 1, "func/f"), _make_site(1, 2, "func/g")]
    covered = {1}  # line 2 uncovered
    _, selected = _select_sites(sites, covered, set(), False, None)
    assert len(selected) == 1
    assert selected[0].line == 1


# ── run_mutations integration ─────────────────────────────────────────────────


def _write_lcov(path: str, source_abs: str, covered_lines: list[int]) -> None:
    da_lines = "\n".join(f"DA:{ln},1" for ln in covered_lines)
    content = f"SF:{source_abs}\n{da_lines}\nend_of_record\n"
    with open(path, "w") as f:
        f.write(content)


def _make_pass_script(path: str) -> str:
    """Write a test script that always passes."""
    script = "#!/bin/sh\nexit 0\n"
    with open(path, "w") as f:
        f.write(script)
    os.chmod(path, 0o755)
    return path


def _make_fail_script(path: str) -> str:
    """Write a test script that always fails."""
    script = "#!/bin/sh\nexit 1\n"
    with open(path, "w") as f:
        f.write(script)
    os.chmod(path, 0o755)
    return path


def _make_kill_if_mutated_script(path: str, source_path: str, mutant_text: str) -> str:
    """Write a test script that fails when the source contains mutant_text."""
    escaped = mutant_text.replace("'", "'\\''")
    script = (
        f"#!/bin/sh\n"
        f"if grep -qF '{escaped}' '{source_path}'; then exit 1; else exit 0; fi\n"
    )
    with open(path, "w") as f:
        f.write(script)
    os.chmod(path, 0o755)
    return path


def test_run_mutations_killed_mutant(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    sites = discover_sites(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov(lcov_path, src_path, [s.line for s in sites])

    script_path = str(tmp_path / "test.sh")
    _make_kill_if_mutated_script(script_path, src_path, sites[0].mutant_text)

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_mutations(
            path=src_path,
            source=src,
            cov_cmd=None,
            lcov_path=lcov_path,
            reuse_coverage=False,
            test_command=f"sh {script_path}",
            timeout_factor=10,
            lines_filter=None,
            since_last_run=False,
            mutate_all=False,
            warning_threshold=1000,
            cwd=str(tmp_path),
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

    script_path = str(tmp_path / "test.sh")
    _make_pass_script(script_path)

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_mutations(
            path=src_path,
            source=src,
            cov_cmd=None,
            lcov_path=lcov_path,
            reuse_coverage=False,
            test_command=f"sh {script_path}",
            timeout_factor=10,
            lines_filter=None,
            since_last_run=False,
            mutate_all=False,
            warning_threshold=1000,
            cwd=str(tmp_path),
        )
    output = buf.getvalue()
    assert rc == 0
    assert "survived" in output
    assert "Survived: 1" in output
    assert "Survivors:" in output


def test_run_mutations_baseline_failure_exits_1(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    sites = discover_sites(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov(lcov_path, src_path, [s.line for s in sites])

    script_path = str(tmp_path / "test.sh")
    _make_fail_script(script_path)

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_mutations(
            path=src_path,
            source=src,
            cov_cmd=None,
            lcov_path=lcov_path,
            reuse_coverage=False,
            test_command=f"sh {script_path}",
            timeout_factor=10,
            lines_filter=None,
            since_last_run=False,
            mutate_all=False,
            warning_threshold=1000,
            cwd=str(tmp_path),
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

    script_path = str(tmp_path / "test.sh")
    _make_pass_script(script_path)

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_mutations(
            path=src_path,
            source=src,
            cov_cmd=None,
            lcov_path=lcov_path,
            reuse_coverage=False,
            test_command=f"sh {script_path}",
            timeout_factor=10,
            lines_filter=None,
            since_last_run=False,
            mutate_all=False,
            warning_threshold=1000,
            cwd=str(tmp_path),
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

    script_path = str(tmp_path / "test.sh")
    _make_pass_script(script_path)

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_mutations(
            path=src_path,
            source=src,
            cov_cmd=None,
            lcov_path=lcov_path,
            reuse_coverage=False,
            test_command=f"sh {script_path}",
            timeout_factor=10,
            lines_filter=None,
            since_last_run=False,
            mutate_all=False,
            warning_threshold=1000,
            cwd=str(tmp_path),
        )
    output = buf.getvalue()
    assert "Restored source from backup" in output


def test_run_mutations_reuse_coverage_warns(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    sites = discover_sites(src)
    # Write to the default coverage.lcov path
    lcov_path = str(tmp_path / "coverage.lcov")
    _write_lcov(lcov_path, src_path, [s.line for s in sites])

    script_path = str(tmp_path / "test.sh")
    _make_pass_script(script_path)

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_mutations(
            path=src_path,
            source=src,
            cov_cmd=None,
            lcov_path=None,
            reuse_coverage=True,
            test_command=f"sh {script_path}",
            timeout_factor=10,
            lines_filter=None,
            since_last_run=False,
            mutate_all=False,
            warning_threshold=1000,
            cwd=str(tmp_path),
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

    script_path = str(tmp_path / "test.sh")
    _make_pass_script(script_path)

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_mutations(
            path=src_path,
            source=src,
            cov_cmd=None,
            lcov_path=lcov_path,
            reuse_coverage=False,
            test_command=f"sh {script_path}",
            timeout_factor=10,
            lines_filter=None,
            since_last_run=False,
            mutate_all=False,
            warning_threshold=1000,
            cwd=str(tmp_path),
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


def test_run_mutations_timeout_counts_as_killed(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    sites = discover_sites(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov(lcov_path, src_path, [s.line for s in sites])

    # Baseline passes quickly, mutant sleeps past the short timeout
    baseline_script = str(tmp_path / "baseline.sh")
    with open(baseline_script, "w") as f:
        f.write("#!/bin/sh\n")
        f.write(
            f"if grep -qF '{sites[0].mutant_text}' '{src_path}'; then sleep 5; fi\n"
        )
        f.write("exit 0\n")
    os.chmod(baseline_script, 0o755)

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        run_mutations(
            path=src_path,
            source=src,
            cov_cmd=None,
            lcov_path=lcov_path,
            reuse_coverage=False,
            test_command=f"sh {baseline_script}",
            timeout_factor=1,
            lines_filter=None,
            since_last_run=False,
            mutate_all=False,
            warning_threshold=1000,
            cwd=str(tmp_path),
        )
    output = buf.getvalue()
    assert "timeout" in output
    assert "Killed: 1" in output  # timeout counts as killed
    assert "Survived: 0" in output


# ── _print_uncovered_block ────────────────────────────────────────────────────


def test_print_uncovered_block_with_uncovered(capsys):
    sites = [
        _make_site(0, 1, "func/f"),
        _make_site(1, 2, "func/g"),
    ]
    covered_lines = {1}  # line 2 is uncovered
    _print_uncovered_block(sites, covered_lines)
    out = capsys.readouterr().out
    assert "Uncovered mutations:" in out
    assert "line 2" in out
    assert "func/g" in out


def test_print_uncovered_block_no_uncovered(capsys):
    sites = [_make_site(0, 1, "func/f"), _make_site(1, 2, "func/g")]
    covered_lines = {1, 2}
    _print_uncovered_block(sites, covered_lines)
    out = capsys.readouterr().out
    assert out == ""


def test_print_uncovered_block_no_function_id(capsys):
    site = Site(
        index=0,
        line=5,
        col=0,
        end_line=5,
        end_col=3,
        function_id="",
        orig_text=">",
        mutant_text=">=",
        desc="> -> >=",
    )
    _print_uncovered_block([site], set())
    out = capsys.readouterr().out
    assert "line 5" in out
    assert "Uncovered mutations:" in out


# ── run_mutations: warning threshold and CoverageError ───────────────────────


def test_run_mutations_warning_threshold_exceeded(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    sites = discover_sites(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov(lcov_path, src_path, [s.line for s in sites])

    script_path = str(tmp_path / "test.sh")
    _make_pass_script(script_path)

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_mutations(
            path=src_path,
            source=src,
            cov_cmd=None,
            lcov_path=lcov_path,
            reuse_coverage=False,
            test_command=f"sh {script_path}",
            timeout_factor=10,
            lines_filter=None,
            since_last_run=False,
            mutate_all=False,
            warning_threshold=0,  # any sites exceed this
            cwd=str(tmp_path),
        )
    output = buf.getvalue()
    assert rc == 0
    assert "Warning:" in output


def test_run_mutations_coverage_error_returns_1(tmp_path, monkeypatch):
    from mutate4py._coverage import CoverageError
    import mutate4py._runner as runner_mod

    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)

    monkeypatch.setattr(
        runner_mod,
        "acquire_coverage",
        lambda **_kw: (_ for _ in ()).throw(CoverageError("no coverage")),
    )

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_mutations(
            path=src_path,
            source=src,
            cov_cmd=None,
            lcov_path=None,
            reuse_coverage=False,
            test_command="exit 0",
            timeout_factor=10,
            lines_filter=None,
            since_last_run=False,
            mutate_all=False,
            warning_threshold=1000,
            cwd=str(tmp_path),
        )
    output = buf.getvalue()
    assert rc == 1
    assert "error:" in output
