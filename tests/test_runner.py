"""Unit tests for F4 run loop (_runner.py)."""

import os


from mutate4py._discovery import Site, apply_mutant, discover_sites
from mutate4py._runner import (
    _baseline_reason,
    _finalize_source,
    _is_effective_since_last_run,
    _on_parallel_result,
    _print_uncovered_block,
    _run_mutation_loop,
    _run_parallel_workers,
    _select_sites,
    _should_run_parallel,
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
    n_sites = len(sites)
    assert rc == 0
    assert "survived" in output
    assert "Survived: 1" in output
    assert "Survivors:" in output
    assert f"[1/{n_sites}]" in output


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

    result = subprocess.CompletedProcess(
        args=[], returncode=1, stderr=b"test suite crashed\nsecond line"
    )
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


# ── F6 parallel workers — serial/parallel switch ──────────────────────────────


def _make_multi_site_source(n_funcs: int) -> str:
    lines = []
    for i in range(1, n_funcs + 1):
        lines.append(f"def f{i}(a, b):")
        lines.append(f"    return a > b")
        lines.append("")
    return "\n".join(lines) + "\n"


def _write_lcov_for_source(lcov_path: str, src_path: str, source: str) -> None:
    from mutate4py._discovery import discover_sites
    sites = discover_sites(source)
    _write_lcov(lcov_path, src_path, [s.line for s in sites])


def _run_with_capture(tmp_path, src_path, src, *, max_workers, test_cmd="exit 0"):
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov_for_source(lcov_path, src_path, src)
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
            test_command=test_cmd,
            timeout_factor=10,
            lines_filter=None,
            since_last_run=False,
            mutate_all=False,
            warning_threshold=1000,
            max_workers=max_workers,
            cwd=str(tmp_path),
        )
    return rc, buf.getvalue()


def test_serial_path_no_workers_header(tmp_path):
    """max_workers=0 -> no 'Mutation workers:' line."""
    src = _make_multi_site_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    _, output = _run_with_capture(tmp_path, src_path, src, max_workers=0)
    assert "Mutation workers:" not in output


def test_serial_path_workers_header_max_workers_1(tmp_path):
    """max_workers=1 (serial path, 3 sites) -> prints 'Mutation workers: 1', no worker-k in progress."""
    src = _make_multi_site_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    _, output = _run_with_capture(tmp_path, src_path, src, max_workers=1)
    assert "Mutation workers: 1" in output
    for line in output.splitlines():
        if line.startswith("["):
            assert "worker-" not in line, f"Serial path has worker token: {line}"


def test_serial_switch_one_site(tmp_path):
    """max_workers=4, only 1 site -> serial path (no worker-k token)."""
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    _, output = _run_with_capture(tmp_path, src_path, src, max_workers=4)
    for line in output.splitlines():
        if line.startswith("["):
            assert "worker-" not in line, f"Expected serial progress: {line}"


def test_parallel_path_workers_header_clamped(tmp_path, monkeypatch):
    """max_workers=8, 3 sites -> 'Mutation workers: 3' (clamped); provisioning skipped."""
    import mutate4py._workers as workers_mod
    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root: None)

    src = _make_multi_site_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    _, output = _run_with_capture(tmp_path, src_path, src, max_workers=8)
    assert "Mutation workers: 3" in output


def test_parallel_path_worker_token_in_progress(tmp_path, monkeypatch):
    """Parallel path (max_workers=4, 4 sites) -> worker-k appears in progress lines."""
    import mutate4py._workers as workers_mod
    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root: None)

    src = _make_multi_site_source(4)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    _, output = _run_with_capture(tmp_path, src_path, src, max_workers=4)
    progress_lines = [ln for ln in output.splitlines() if ln.startswith("[")]
    assert progress_lines, "No progress lines in output"
    for line in progress_lines:
        assert "worker-" in line, f"Parallel progress line missing worker token: {line}"


def test_parallel_path_report_present(tmp_path, monkeypatch):
    """Parallel run produces a Mutation Report."""
    import mutate4py._workers as workers_mod
    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root: None)

    src = _make_multi_site_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    rc, output = _run_with_capture(tmp_path, src_path, src, max_workers=3)
    assert rc == 0
    assert "Mutation Report" in output


def test_parallel_path_target_outside_cwd_error(tmp_path, monkeypatch):
    """Target file outside cwd -> error, no worker root created."""
    import tempfile
    import mutate4py._workers as workers_mod
    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root: None)

    with tempfile.TemporaryDirectory() as other_dir:
        src = _make_multi_site_source(3)
        src_path = os.path.join(other_dir, "calc.py")
        with open(src_path, "w") as f:
            f.write(src)

        lcov_path = str(tmp_path / "cov.lcov")
        _write_lcov_for_source(lcov_path, src_path, src)

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
                test_command="exit 0",
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                max_workers=4,
                cwd=str(tmp_path),
            )
        output = buf.getvalue()
        assert rc == 1
        assert "must be inside working directory" in output
        workers_dir = os.path.join(str(tmp_path), ".mutate4py", "workers")
        assert not os.path.exists(workers_dir)


def test_parallel_path_worker_root_cleaned_up(tmp_path, monkeypatch):
    """After parallel run, worker root is removed."""
    import mutate4py._workers as workers_mod
    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root: None)

    src = _make_multi_site_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    rc, _ = _run_with_capture(tmp_path, src_path, src, max_workers=3)
    assert rc == 0
    workers_dir = os.path.join(str(tmp_path), ".mutate4py", "workers")
    if os.path.exists(workers_dir):
        assert os.listdir(workers_dir) == []


def test_parallel_path_original_file_restored(tmp_path, monkeypatch):
    """After parallel run, original source has no mutant; manifest footer present."""
    from mutate4py._manifest import strip_manifest
    import mutate4py._workers as workers_mod
    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root: None)

    src = _make_multi_site_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    rc, _ = _run_with_capture(tmp_path, src_path, src, max_workers=3)
    assert rc == 0
    with open(src_path) as f:
        final = f.read()
    body = strip_manifest(final)
    assert ">=" not in body
    assert "mutate4py-manifest-begin" in final


# ── _run_mutation_loop ────────────────────────────────────────────────────────


def test_run_mutation_loop_empty_sites_returns_zero_counts(tmp_path):
    """Zero selected sites means all counts start and stay at zero — kills initial-value mutants."""
    src_file = tmp_path / "calc.py"
    src_file.write_text("x = 1\n")
    counts, survivors = _run_mutation_loop(
        selected_sites=[],
        clean_source="x = 1\n",
        path=str(src_file),
        source_dir=str(tmp_path),
        test_command="exit 0",
        mutant_timeout=5.0,
    )
    assert counts == {"killed": 0, "timeout": 0, "survived": 0}
    assert survivors == []


# ── _should_run_parallel boundary conditions ──────────────────────────────────


def test_should_run_parallel_exact_boundary():
    """max_workers=2, n_selected=2 -> parallel (inclusive on both)."""
    assert _should_run_parallel(max_workers=2, n_selected=2) is True


def test_should_run_parallel_one_worker():
    """max_workers=1 -> serial even with many sites."""
    assert _should_run_parallel(max_workers=1, n_selected=10) is False


def test_should_run_parallel_one_site():
    """n_selected=1 -> serial even with many workers."""
    assert _should_run_parallel(max_workers=8, n_selected=1) is False


def test_should_run_parallel_two_workers_one_site():
    """max_workers=2, n_selected=1 -> serial."""
    assert _should_run_parallel(max_workers=2, n_selected=1) is False


def test_should_run_parallel_three_workers():
    """max_workers=3, n_selected=2 -> parallel."""
    assert _should_run_parallel(max_workers=3, n_selected=2) is True


# ── _is_effective_since_last_run logic ───────────────────────────────────────


def test_is_effective_since_last_run_explicit():
    """since_last_run=True -> effective regardless of other flags."""
    assert _is_effective_since_last_run(True, False, True, {1, 2}) is True


def test_is_effective_since_last_run_implicit_all_conditions():
    """manifest exists, mutate_all=False, no lines_filter -> effective."""
    assert _is_effective_since_last_run(False, True, False, None) is True


def test_is_effective_since_last_run_no_manifest():
    """No manifest -> not effective via implicit path."""
    assert _is_effective_since_last_run(False, False, False, None) is False


def test_is_effective_since_last_run_mutate_all_disables():
    """mutate_all=True -> not effective via implicit path."""
    assert _is_effective_since_last_run(False, True, True, None) is False


def test_is_effective_since_last_run_lines_filter_disables():
    """lines_filter present -> not effective via implicit path."""
    assert _is_effective_since_last_run(False, True, False, {5}) is False


# ── _on_parallel_result output ────────────────────────────────────────────────


def _make_simple_site(line=42, function_id=""):
    return Site(
        index=0,
        line=line,
        col=11,
        end_line=line,
        end_col=12,
        function_id=function_id,
        orig_text=">",
        mutant_text=">=",
        desc="> -> >=",
    )


def test_on_parallel_result_includes_worker_idx(capsys):
    """worker_idx from result dict must appear in the printed progress line."""
    result = {
        "site": _make_simple_site(42),
        "site_idx": 3,
        "total": 10,
        "worker_idx": 7,
        "status": "survived",
    }
    _on_parallel_result(result)
    out = capsys.readouterr().out
    assert "worker-7" in out
    assert "[3/10]" in out


def test_on_parallel_result_different_worker_idx(capsys):
    """A different worker_idx produces a different label — ensures idx is not hardcoded."""
    result = {"site": _make_simple_site(1), "site_idx": 1, "total": 5, "worker_idx": 2, "status": "killed"}
    _on_parallel_result(result)
    out = capsys.readouterr().out
    assert "worker-2" in out
    assert "worker-7" not in out


def test_on_parallel_result_fid_suffix_when_empty(capsys):
    """When function_id is empty, no trailing colon-suffix in the output line."""
    result = {
        "site": _make_simple_site(10, function_id=""),
        "site_idx": 1,
        "total": 1,
        "worker_idx": 1,
        "status": "killed",
    }
    _on_parallel_result(result)
    out = capsys.readouterr().out
    assert out.rstrip("\n").endswith("> -> >="), f"No extra suffix expected, got: {out!r}"


def test_on_parallel_result_fid_suffix_when_present(capsys):
    """When function_id is non-empty, the line ends with ': <function_id>'."""
    result = {
        "site": _make_simple_site(10, function_id="func/calc"),
        "site_idx": 2,
        "total": 4,
        "worker_idx": 3,
        "status": "killed",
    }
    _on_parallel_result(result)
    out = capsys.readouterr().out
    assert ": func/calc" in out, f"Expected fid suffix, got: {out!r}"


# ── _run_parallel_workers passes mutant_timeout ───────────────────────────────


def test_run_parallel_workers_passes_timeout(tmp_path, monkeypatch):
    """mutant_timeout is forwarded to run_parallel (not silently replaced with None)."""
    import mutate4py._workers as workers_mod

    captured = {}

    def fake_run_parallel(*, mutant_timeout, **_kw):
        captured["mutant_timeout"] = mutant_timeout
        return ({"killed": 0, "survived": 0, "timeout": 0}, [])

    monkeypatch.setattr(workers_mod, "run_parallel", fake_run_parallel)
    monkeypatch.setattr(workers_mod, "_provision_worker", lambda root: None)

    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "f.py")
    with open(src_path, "w") as f:
        f.write(src)

    from mutate4py._discovery import discover_sites
    sites = discover_sites(src)

    _run_parallel_workers(
        selected_sites=sites,
        clean_source=src,
        path=src_path,
        cwd=str(tmp_path),
        test_command="exit 0",
        mutant_timeout=42.0,
        max_workers=2,
    )
    assert captured["mutant_timeout"] == 42.0


# ── _finalize_source manifest content ────────────────────────────────────────


def test_finalize_source_embeds_manifest_with_tested_at(tmp_path):
    """_finalize_source writes the file with a manifest containing the tested_at timestamp."""
    import json
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "f.py")
    bak_path = src_path + ".bak"
    with open(src_path, "w") as f:
        f.write(src)

    tested_at = "2026-01-01T00:00:00Z"
    _finalize_source(src_path, src, tested_at, bak_path)

    with open(src_path) as f:
        content = f.read()

    assert "mutate4py-manifest-begin" in content
    manifest_line = [ln for ln in content.splitlines() if ln.startswith("# {")][0]
    manifest = json.loads(manifest_line[2:])
    assert manifest["tested_at"] == tested_at


def test_finalize_source_removes_bak_when_present(tmp_path):
    """_finalize_source removes the .bak file if it exists after writing."""
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "f.py")
    bak_path = src_path + ".bak"
    with open(src_path, "w") as f:
        f.write(src)
    with open(bak_path, "w") as f:
        f.write(src)

    _finalize_source(src_path, src, "2026-01-01T00:00:00Z", bak_path)

    assert not os.path.isfile(bak_path)


def test_finalize_source_manifest_is_valid_dict(tmp_path):
    """The embedded manifest is valid JSON dict (not null, not a string)."""
    import json
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "f.py")
    bak_path = src_path + ".bak"
    with open(src_path, "w") as f:
        f.write(src)

    _finalize_source(src_path, src, "2026-01-01T00:00:00Z", bak_path)

    with open(src_path) as f:
        content = f.read()

    manifest_line = [ln for ln in content.splitlines() if ln.startswith("# {")][0]
    manifest = json.loads(manifest_line[2:])
    assert isinstance(manifest, dict)
    assert "sites" in manifest or "ast_hash" in manifest or "tested_at" in manifest
