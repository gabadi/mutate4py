"""Unit tests for F4 run loop (_runner.py)."""

import os

import pytest

from mutate4py._discovery import Site, apply_mutant, discover_sites
from mutate4py._manifest import build_manifest, embed_manifest
from mutate4py._runner import (
    CoverageSource,
    ManifestLocation,
    MutantExecCtx,
    RunMutationsRequest,
    RunStats,
    _baseline_reason,
    _finalize_source,
    _fork_server_eligible,
    _is_effective_since_last_run,
    _mutation_report_lines,
    _on_parallel_result,
    _parallel_progress_line,
    _run_header_lines,
    _run_mutation_loop,
    _run_parallel_workers,
    _run_single_mutant,
    _select_sites,
    _serial_progress_line,
    _should_run_parallel,
    _uncovered_block_lines,
    _workers_header_lines,
    check_manifest,
    read_sidecar_manifest,
    run_mutations,
    run_scan,
    update_manifest,
    write_sidecar_manifest,
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
    _, selected = _select_sites(sites, covered, set(), effective_since_last_run=False, lines_filter=None)
    assert len(selected) == 2


def test_select_sites_differential_filters_unchanged():
    sites = [_make_site(0, 1, "func/f"), _make_site(1, 2, "func/g")]
    covered = {1, 2}
    changed = {"func/f"}
    _, selected = _select_sites(sites, covered, changed, effective_since_last_run=True, lines_filter=None)
    assert len(selected) == 1
    assert selected[0].function_id == "func/f"


def test_select_sites_lines_filter():
    sites = [_make_site(0, 1, "func/f"), _make_site(1, 2, "func/g")]
    covered = {1, 2}
    _, selected = _select_sites(sites, covered, set(), effective_since_last_run=False, lines_filter={1})
    assert len(selected) == 1
    assert selected[0].line == 1


def test_select_sites_uncovered_excluded():
    sites = [_make_site(0, 1, "func/f"), _make_site(1, 2, "func/g")]
    covered = {1}  # line 2 uncovered
    _, selected = _select_sites(sites, covered, set(), effective_since_last_run=False, lines_filter=None)
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
    script = f"#!/bin/sh\nif grep -qF '{escaped}' '{source_path}'; then exit 1; else exit 0; fi\n"
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
            RunMutationsRequest(
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
            RunMutationsRequest(
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

    script_path = str(tmp_path / "test.sh")
    _make_pass_script(script_path)

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
                test_command=f"sh {script_path}",
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

    script_path = str(tmp_path / "test.sh")
    _make_fail_script(script_path)

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
                test_command=f"sh {script_path}",
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

    script_path = str(tmp_path / "test.sh")
    _make_pass_script(script_path)

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
                test_command=f"sh {script_path}",
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

    script_path = str(tmp_path / "test.sh")
    _make_pass_script(script_path)

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
                test_command=f"sh {script_path}",
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

    script_path = str(tmp_path / "test.sh")
    _make_pass_script(script_path)

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
                test_command=f"sh {script_path}",
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

    script_path = str(tmp_path / "test.sh")
    _make_pass_script(script_path)

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
                test_command=f"sh {script_path}",
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

    script_path = str(tmp_path / "test.sh")
    _make_pass_script(script_path)

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
                test_command=f"sh {script_path}",
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
        f.write(f"if grep -qF '{sites[0].mutant_text}' '{src_path}'; then sleep 5; fi\n")
        f.write("exit 0\n")
    os.chmod(baseline_script, 0o755)

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
                test_command=f"sh {baseline_script}",
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


# ── _uncovered_block_lines ────────────────────────────────────────────────────


def test_uncovered_block_lines_with_uncovered():
    sites = [
        _make_site(0, 1, "func/f"),
        _make_site(1, 2, "func/g"),
    ]
    covered_lines = {1}  # line 2 is uncovered
    lines = _uncovered_block_lines(sites, covered_lines)
    assert lines[0] == "Uncovered mutations:"
    assert any("line 2" in ln and "func/g" in ln for ln in lines)


def test_uncovered_block_lines_no_uncovered():
    sites = [_make_site(0, 1, "func/f"), _make_site(1, 2, "func/g")]
    covered_lines = {1, 2}
    assert _uncovered_block_lines(sites, covered_lines) == []


def test_uncovered_block_lines_no_function_id():
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
    lines = _uncovered_block_lines([site], set())
    assert lines == ["Uncovered mutations:", "  line 5 > -> >="]


# ── _run_header_lines ─────────────────────────────────────────────────────────


def _make_run_stats(**overrides) -> RunStats:
    defaults = dict(
        total=5,
        covered_count=4,
        uncovered_count=1,
        changed_count=5,
        manifest_exists=False,
        selected_count=4,
        warning_threshold=1000,
    )
    defaults.update(overrides)
    return RunStats(**defaults)


def test_run_header_lines_field_order_and_content():
    lines = _run_header_lines("calc.py", _make_run_stats())
    assert lines == [
        "Mutation run: calc.py",
        "Total mutation sites: 5",
        "Covered mutation sites: 4",
        "Uncovered mutation sites: 1",
        "Changed mutation sites: 5",
        "Manifest exists: false",
        "Selected mutation sites: 4",
    ]


def test_run_header_lines_manifest_exists_true():
    lines = _run_header_lines("calc.py", _make_run_stats(manifest_exists=True))
    assert "Manifest exists: true" in lines


def test_run_header_lines_warning_above_threshold():
    lines = _run_header_lines("calc.py", _make_run_stats(total=2000, warning_threshold=1000))
    assert lines[-1] == "Warning: 2000 mutation sites exceeds threshold 1000."


def test_run_header_lines_no_warning_at_threshold():
    lines = _run_header_lines("calc.py", _make_run_stats(total=1000, warning_threshold=1000))
    assert not any(ln.startswith("Warning:") for ln in lines)


# ── _workers_header_lines ─────────────────────────────────────────────────────


def test_workers_header_lines_zero_workers_is_empty():
    assert _workers_header_lines(0, use_parallel=False, n_selected=3) == []


def test_workers_header_lines_serial():
    assert _workers_header_lines(1, use_parallel=False, n_selected=3) == ["Mutation workers: 1"]


def test_workers_header_lines_parallel_clamped_to_selected():
    assert _workers_header_lines(8, use_parallel=True, n_selected=3) == ["Mutation workers: 3"]


def test_workers_header_lines_parallel_not_clamped():
    assert _workers_header_lines(2, use_parallel=True, n_selected=5) == ["Mutation workers: 2"]


# ── _serial_progress_line ─────────────────────────────────────────────────────


def test_serial_progress_line_with_function_id():
    site = _make_site(0, 7, "func/f")
    line = _serial_progress_line(2, 5, "survived", site)
    assert line == "[2/5] survived line 7 > -> >=: func/f"


def test_serial_progress_line_without_function_id():
    site = _make_site(0, 7, "")
    line = _serial_progress_line(2, 5, "killed", site)
    assert line == "[2/5] killed line 7 > -> >="


# ── _mutation_report_lines ────────────────────────────────────────────────────


def test_mutation_report_lines_no_survivors():
    lines = _mutation_report_lines({"killed": 2, "timeout": 1, "survived": 0}, [], uncovered_count=1)
    assert lines == [
        "",
        "Mutation Report",
        "===============",
        "Killed: 3",
        "Survived: 0",
        "Uncovered: 1",
    ]


def test_mutation_report_lines_with_survivors():
    survivor = _make_site(0, 4, "func/f")
    lines = _mutation_report_lines({"killed": 0, "timeout": 0, "survived": 1}, [survivor], uncovered_count=0)
    assert lines[-3:] == ["", "Survivors:", "  line 4 > -> >= func/f"]


def test_mutation_report_lines_selection_counts_included():
    lines = _mutation_report_lines(
        {"killed": 1, "timeout": 0, "survived": 0},
        [],
        uncovered_count=0,
        selection_counts={"narrowed": 3, "static": 1},
    )
    assert "Test selection: narrowed 3, static 1" in lines


def test_mutation_report_lines_omits_selection_line_without_a_context_db():
    lines = _mutation_report_lines({"killed": 1, "timeout": 0, "survived": 0}, [], uncovered_count=0)
    assert not any(ln.startswith("Test selection:") for ln in lines)


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
            RunMutationsRequest(
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
            RunMutationsRequest(
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
        )
    output = buf.getvalue()
    assert rc == 1
    assert "error:" in output


# ── F6 parallel workers — serial/parallel switch ──────────────────────────────


def _make_multi_site_source(n_funcs: int) -> str:
    lines = []
    for i in range(1, n_funcs + 1):
        lines.append(f"def f{i}(a, b):")
        lines.append("    return a > b")
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
            RunMutationsRequest(
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
                RunMutationsRequest(
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


# ── _build_mutant_command ───────────────────────────────────────────────────────


class _FakeTestContextDB:
    def __init__(self, outcome, node_ids=()):
        self._result = (outcome, list(node_ids))

    def tests_for_line(self, source_path, line):
        return self._result


def _one_site(src="def f(a, b):\n    return a > b\n"):
    return discover_sites(src)[0]


def test_build_mutant_command_no_ctx_db_returns_full_command():
    from mutate4py._runner import _build_mutant_command

    assert _build_mutant_command("pytest", None, "/src/calc.py", _one_site()) == (
        "pytest",
        None,
    )


def test_build_mutant_command_narrows_to_covering_tests():
    from mutate4py._runner import _build_mutant_command

    ctx_db = _FakeTestContextDB("narrowed", ["tests/test_calc.py::test_gt"])
    assert _build_mutant_command("pytest", ctx_db, "/src/calc.py", _one_site()) == (
        "pytest tests/test_calc.py::test_gt",
        "narrowed",
    )


def test_build_mutant_command_quotes_node_ids():
    from mutate4py._runner import _build_mutant_command

    ctx_db = _FakeTestContextDB("narrowed", ["tests/t.py::test_a[x y]"])
    cmd, _ = _build_mutant_command("pytest", ctx_db, "/src/calc.py", _one_site())
    assert cmd == "pytest 'tests/t.py::test_a[x y]'"


def test_build_mutant_command_static_line_runs_full_command():
    from mutate4py._runner import _build_mutant_command

    ctx_db = _FakeTestContextDB("static")
    assert _build_mutant_command("pytest", ctx_db, "/src/calc.py", _one_site()) == (
        "pytest",
        "static",
    )


@pytest.mark.parametrize(
    "outcome, hint",
    [
        ("line-absent", "absent from the test-context db"),
        ("file-absent", "not in the test-context db"),
    ],
)
def test_build_mutant_command_disagreement_raises(outcome, hint):
    from mutate4py._runner import TestSelectionError, _build_mutant_command

    ctx_db = _FakeTestContextDB(outcome)
    with pytest.raises(TestSelectionError) as excinfo:
        _build_mutant_command("pytest", ctx_db, "/src/calc.py", _one_site())
    message = str(excinfo.value)
    assert "/src/calc.py:2" in message
    assert hint in message


def test_build_mutant_command_unrecognized_outcome_raises():
    """No outcome may fall through to a full-suite run counted as narrowed."""
    from mutate4py._runner import TestSelectionError, _build_mutant_command

    ctx_db = _FakeTestContextDB("something-new")
    with pytest.raises(TestSelectionError, match="unrecognized selection outcome"):
        _build_mutant_command("pytest", ctx_db, "/src/calc.py", _one_site())


# ── _run_mutation_loop ────────────────────────────────────────────────────────


def test_run_mutation_loop_empty_sites_returns_zero_counts(tmp_path):
    """Zero selected sites means all counts start and stay at zero — kills initial-value mutants."""
    src_file = tmp_path / "calc.py"
    src_file.write_text("x = 1\n")
    counts, survivors, selection_counts = _run_mutation_loop(
        selected_sites=[],
        clean_source="x = 1\n",
        ctx=MutantExecCtx(
            path=str(src_file),
            cwd=str(tmp_path),
            test_command="exit 0",
            mutant_timeout=5.0,
        ),
    )
    assert counts == {"killed": 0, "timeout": 0, "survived": 0}
    assert survivors == []
    assert selection_counts is None


def _loop_over_two_sites(tmp_path, ctx_db):
    src = "def f(a, b):\n    return a > b\n\n\ndef g(a, b):\n    return a + b\n"
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    return _run_mutation_loop(
        selected_sites=discover_sites(src),
        clean_source=src,
        ctx=MutantExecCtx(
            path=str(src_file),
            cwd=str(tmp_path),
            test_command="exit 1",
            mutant_timeout=5.0,
            test_ctx_db=ctx_db,
            abs_source_path=str(src_file),
        ),
    )


def test_run_mutation_loop_tallies_narrowed_selections(tmp_path):
    _, _, selection_counts = _loop_over_two_sites(
        tmp_path, _FakeTestContextDB("narrowed", ["tests/test_calc.py::test_f"])
    )
    assert selection_counts == {"narrowed": 2, "static": 0}


def test_run_mutation_loop_tallies_static_selections(tmp_path):
    _, _, selection_counts = _loop_over_two_sites(tmp_path, _FakeTestContextDB("static"))
    assert selection_counts == {"narrowed": 0, "static": 2}


def test_run_mutation_loop_disagreement_aborts_before_applying_the_mutant(tmp_path):
    from mutate4py._runner import TestSelectionError

    src = "def f(a, b):\n    return a > b\n"
    src_file = tmp_path / "calc.py"
    src_file.write_text(src)
    with pytest.raises(TestSelectionError):
        _run_mutation_loop(
            selected_sites=discover_sites(src),
            clean_source=src,
            ctx=MutantExecCtx(
                path=str(src_file),
                cwd=str(tmp_path),
                test_command="exit 1",
                mutant_timeout=5.0,
                test_ctx_db=_FakeTestContextDB("line-absent"),
                abs_source_path=str(src_file),
            ),
        )
    assert src_file.read_text() == src


# ── --test-contexts end-to-end: report line and the case-3 abort ──────────────


def _run_with_stub_ctx_db(tmp_path, monkeypatch, outcome, node_ids=(), *, test_contexts=".coverage"):
    import mutate4py._test_selection as ts

    class _StubDB:
        def __init__(self, db_path):
            self.closed = False

        def tests_for_line(self, source_path, line):
            return outcome, list(node_ids)

        def close(self):
            self.closed = True

    monkeypatch.setattr(ts, "TestContextDB", _StubDB)
    src = _make_multi_site_source(3)
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(src)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov_for_source(lcov_path, src_path, src)
    rc = run_mutations(
        RunMutationsRequest(
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
            cwd=str(tmp_path),
            test_contexts_path=test_contexts,
        )
    )
    return rc, src_path, src


def test_report_counts_narrowed_selections(tmp_path, monkeypatch, capsys):
    rc, _, _ = _run_with_stub_ctx_db(tmp_path, monkeypatch, "narrowed", ["tests/test_calc.py::test_f"])
    assert rc == 0
    assert "Test selection: narrowed 3, static 0" in capsys.readouterr().out


def test_report_counts_static_selections(tmp_path, monkeypatch, capsys):
    rc, _, _ = _run_with_stub_ctx_db(tmp_path, monkeypatch, "static")
    assert rc == 0
    assert "Test selection: narrowed 0, static 3" in capsys.readouterr().out


def test_report_omits_test_selection_line_without_a_context_db(tmp_path, monkeypatch, capsys):
    rc, _, _ = _run_with_stub_ctx_db(tmp_path, monkeypatch, "narrowed", test_contexts=None)
    assert rc == 0
    assert "Test selection:" not in capsys.readouterr().out


def test_test_selection_line_sits_after_uncovered_in_the_report(tmp_path, monkeypatch, capsys):
    _run_with_stub_ctx_db(tmp_path, monkeypatch, "static")
    lines = capsys.readouterr().out.splitlines()
    report = lines[lines.index("Mutation Report") :]
    assert report[4].startswith("Uncovered: ")
    assert report[5].startswith("Test selection: ")


@pytest.mark.parametrize("outcome", ["line-absent", "file-absent"])
def test_disagreement_exits_2_with_no_report(tmp_path, monkeypatch, capsys, outcome):
    rc, src_path, src = _run_with_stub_ctx_db(tmp_path, monkeypatch, outcome)
    captured = capsys.readouterr()
    assert rc == 2
    assert "Mutation Report" not in captured.out
    assert "error: test-context db disagrees with coverage" in captured.err
    assert f"{src_path}:2" in captured.err


def test_disagreement_restores_the_source_and_removes_the_backup(tmp_path, monkeypatch, capsys):
    from mutate4py._manifest import strip_manifest

    rc, src_path, src = _run_with_stub_ctx_db(tmp_path, monkeypatch, "line-absent")
    capsys.readouterr()
    assert rc == 2
    with open(src_path) as f:
        final = f.read()
    assert strip_manifest(final).rstrip("\n") == src.rstrip("\n")
    assert not os.path.isfile(src_path + ".bak")


# ── _fork_server_eligible ─────────────────────────────────────────────────────


def test_fork_server_eligible_true_when_all_conditions_met():
    assert (
        _fork_server_eligible(
            fork_server_requested=True, use_parallel=False, test_ctx_db=None, selected_sites=[object()]
        )
        is True
    )


def test_fork_server_eligible_false_when_not_requested():
    assert (
        _fork_server_eligible(
            fork_server_requested=False, use_parallel=False, test_ctx_db=None, selected_sites=[object()]
        )
        is False
    )


def test_fork_server_eligible_false_when_parallel():
    assert (
        _fork_server_eligible(
            fork_server_requested=True, use_parallel=True, test_ctx_db=None, selected_sites=[object()]
        )
        is False
    )


def test_fork_server_eligible_false_when_test_ctx_db_present():
    assert (
        _fork_server_eligible(
            fork_server_requested=True, use_parallel=False, test_ctx_db=object(), selected_sites=[object()]
        )
        is False
    )


def test_fork_server_eligible_false_when_no_selected_sites():
    assert (
        _fork_server_eligible(fork_server_requested=True, use_parallel=False, test_ctx_db=None, selected_sites=[])
        is False
    )


# ── _run_single_mutant ────────────────────────────────────────────────────────


def test_run_single_mutant_uses_fork_server_when_given():
    class FakeForkServer:
        def run(self, timeout):
            return "survived", False

    status = _run_single_mutant(FakeForkServer(), "pytest", "/cwd", 5.0)
    assert status == "survived"


def test_run_single_mutant_falls_back_to_subprocess_when_no_fork_server():
    status = _run_single_mutant(None, "exit 1", "/tmp", 5.0)
    assert status == "killed"


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
    assert (
        _is_effective_since_last_run(since_last_run=True, manifest_exists=False, mutate_all=True, lines_filter={1, 2})
        is True
    )


def test_is_effective_since_last_run_implicit_all_conditions():
    """manifest exists, mutate_all=False, no lines_filter -> effective."""
    assert (
        _is_effective_since_last_run(since_last_run=False, manifest_exists=True, mutate_all=False, lines_filter=None)
        is True
    )


def test_is_effective_since_last_run_no_manifest():
    """No manifest -> not effective via implicit path."""
    assert (
        _is_effective_since_last_run(since_last_run=False, manifest_exists=False, mutate_all=False, lines_filter=None)
        is False
    )


def test_is_effective_since_last_run_mutate_all_disables():
    """mutate_all=True -> not effective via implicit path."""
    assert (
        _is_effective_since_last_run(since_last_run=False, manifest_exists=True, mutate_all=True, lines_filter=None)
        is False
    )


def test_is_effective_since_last_run_lines_filter_disables():
    """lines_filter present -> not effective via implicit path."""
    assert (
        _is_effective_since_last_run(since_last_run=False, manifest_exists=True, mutate_all=False, lines_filter={5})
        is False
    )


# ── _parallel_progress_line ───────────────────────────────────────────────────


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


def test_parallel_progress_line_includes_worker_idx():
    """worker_idx from result dict must appear in the formatted progress line."""
    result = {
        "site": _make_simple_site(42),
        "site_idx": 3,
        "total": 10,
        "worker_idx": 7,
        "status": "survived",
    }
    line = _parallel_progress_line(result)
    assert "worker-7" in line
    assert "[3/10]" in line


def test_parallel_progress_line_different_worker_idx():
    """A different worker_idx produces a different label — ensures idx is not hardcoded."""
    result = {
        "site": _make_simple_site(1),
        "site_idx": 1,
        "total": 5,
        "worker_idx": 2,
        "status": "killed",
    }
    line = _parallel_progress_line(result)
    assert "worker-2" in line
    assert "worker-7" not in line


def test_parallel_progress_line_fid_suffix_when_empty():
    """When function_id is empty, no trailing colon-suffix in the line."""
    result = {
        "site": _make_simple_site(10, function_id=""),
        "site_idx": 1,
        "total": 1,
        "worker_idx": 1,
        "status": "killed",
    }
    line = _parallel_progress_line(result)
    assert line.endswith("> -> >="), f"No extra suffix expected, got: {line!r}"


def test_parallel_progress_line_fid_suffix_when_present():
    """When function_id is non-empty, the line ends with ': <function_id>'."""
    result = {
        "site": _make_simple_site(10, function_id="func/calc"),
        "site_idx": 2,
        "total": 4,
        "worker_idx": 3,
        "status": "killed",
    }
    line = _parallel_progress_line(result)
    assert ": func/calc" in line, f"Expected fid suffix, got: {line!r}"


def test_on_parallel_result_prints_the_formatted_line(capsys):
    """The print callback delegates to _parallel_progress_line verbatim."""
    result = {
        "site": _make_simple_site(42),
        "site_idx": 3,
        "total": 10,
        "worker_idx": 7,
        "status": "survived",
    }
    _on_parallel_result(result)
    out = capsys.readouterr().out
    assert out == _parallel_progress_line(result) + "\n"


# ── _run_parallel_workers passes mutant_timeout ───────────────────────────────


def test_run_parallel_workers_passes_timeout(tmp_path, monkeypatch):
    """mutant_timeout is forwarded to run_parallel (not silently replaced with None)."""
    import mutate4py._workers as workers_mod

    captured = {}

    def fake_run_parallel(request):
        captured["mutant_timeout"] = request.mutant_timeout
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
        ctx=MutantExecCtx(
            path=src_path,
            cwd=str(tmp_path),
            test_command="exit 0",
            mutant_timeout=42.0,
            max_workers=2,
        ),
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
    _finalize_source(src, tested_at, bak_path, ManifestLocation(path=src_path))

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

    _finalize_source(src, "2026-01-01T00:00:00Z", bak_path, ManifestLocation(path=src_path))

    assert not os.path.isfile(bak_path)


def test_finalize_source_manifest_is_valid_dict(tmp_path):
    """The embedded manifest is valid JSON dict (not null, not a string)."""
    import json

    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "f.py")
    bak_path = src_path + ".bak"
    with open(src_path, "w") as f:
        f.write(src)

    _finalize_source(src, "2026-01-01T00:00:00Z", bak_path, ManifestLocation(path=src_path))

    with open(src_path) as f:
        content = f.read()

    manifest_line = [ln for ln in content.splitlines() if ln.startswith("# {")][0]
    manifest = json.loads(manifest_line[2:])
    assert isinstance(manifest, dict)
    assert "sites" in manifest or "ast_hash" in manifest or "tested_at" in manifest


def test_finalize_source_sidecar_writes_manifest_file_not_footer(tmp_path):
    """manifest_file=True => sidecar JSON gets the manifest; source stays footer-free."""
    import json

    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "f.py")
    bak_path = src_path + ".bak"
    with open(src_path, "w") as f:
        f.write(src)
    sidecar_path = src_path + ".manifest.json"

    _finalize_source(src, "2026-01-01T00:00:00Z", bak_path, ManifestLocation(path=src_path, manifest_file=True))

    with open(src_path) as f:
        content = f.read()
    assert content == src
    assert "mutate4py-manifest-begin" not in content

    with open(sidecar_path) as f:
        sidecar = json.load(f)
    assert sidecar["tested_at"] == "2026-01-01T00:00:00Z"
    assert sidecar["functions"][0]["id"] == "func/f"


def test_finalize_source_sidecar_removes_bak_when_present(tmp_path):
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "f.py")
    bak_path = src_path + ".bak"
    with open(src_path, "w") as f:
        f.write(src)
    with open(bak_path, "w") as f:
        f.write(src)

    _finalize_source(src, "2026-01-01T00:00:00Z", bak_path, ManifestLocation(path=src_path, manifest_file=True))

    assert not os.path.isfile(bak_path)


def test_finalize_source_retains_existing_manifest_when_structurally_equal(tmp_path):
    """When existing_manifest matches the candidate built from clean_source, the OLD
    tested_at is kept in the written file rather than being bumped to the new one."""
    import json

    from mutate4py._manifest import build_manifest

    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "f.py")
    bak_path = src_path + ".bak"
    with open(src_path, "w") as f:
        f.write(src)

    old_tested_at = "2020-01-01T00:00:00Z"
    existing_manifest = build_manifest(src, tested_at=old_tested_at)

    _finalize_source(
        src,
        "2026-01-01T00:00:00Z",
        bak_path,
        ManifestLocation(path=src_path),
        existing_manifest=existing_manifest,
    )

    with open(src_path) as f:
        content = f.read()
    manifest_line = [ln for ln in content.splitlines() if ln.startswith("# {")][0]
    manifest = json.loads(manifest_line[2:])
    assert manifest["tested_at"] == old_tested_at


def test_finalize_source_bumps_tested_at_when_existing_manifest_differs(tmp_path):
    """When existing_manifest is structurally different from the candidate, a fresh
    manifest with the new tested_at is embedded (today's default behavior)."""
    import json

    from mutate4py._manifest import build_manifest

    old_src = "def f(a, b):\n    return a > b\n"
    new_src = "def f(a, b):\n    return a >= b\n"
    src_path = str(tmp_path / "f.py")
    bak_path = src_path + ".bak"
    with open(src_path, "w") as f:
        f.write(new_src)

    old_tested_at = "2020-01-01T00:00:00Z"
    existing_manifest = build_manifest(old_src, tested_at=old_tested_at)
    new_tested_at = "2026-01-01T00:00:00Z"

    _finalize_source(
        new_src,
        new_tested_at,
        bak_path,
        ManifestLocation(path=src_path),
        existing_manifest=existing_manifest,
    )

    with open(src_path) as f:
        content = f.read()
    manifest_line = [ln for ln in content.splitlines() if ln.startswith("# {")][0]
    manifest = json.loads(manifest_line[2:])
    assert manifest["tested_at"] == new_tested_at


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
                test_command="true",
                timeout_factor=10,
                lines_filter=None,
                since_last_run=False,
                mutate_all=False,
                warning_threshold=1000,
                cwd=str(tmp_path),
            )
        )


# ── read_sidecar_manifest / write_sidecar_manifest (sidecar file IO) ──────────


def test_read_sidecar_manifest_missing_file_returns_none_false(tmp_path):
    p = tmp_path / "mod.py"
    assert read_sidecar_manifest(str(p)) == (None, False)


def test_read_sidecar_manifest_invalid_json_returns_none_false(tmp_path):
    p = tmp_path / "mod.py"
    (tmp_path / "mod.py.manifest.json").write_text("not-json")
    assert read_sidecar_manifest(str(p)) == (None, False)


def test_read_sidecar_manifest_non_dict_json_returns_none_false(tmp_path):
    """Valid JSON that isn't an object (e.g. a hand-corrupted sidecar) must not
    be treated as a real manifest — it should read as missing so the next
    --update-manifest overwrites it with a fresh one."""
    p = tmp_path / "mod.py"
    (tmp_path / "mod.py.manifest.json").write_text("[1, 2, 3]")
    assert read_sidecar_manifest(str(p)) == (None, False)


def test_write_sidecar_manifest_round_trips_through_read(tmp_path):
    p = tmp_path / "mod.py"
    m = {
        "version": 1,
        "tested_at": "2026-01-01T00:00:00Z",
        "module_hash": "abc",
        "functions": [],
    }
    write_sidecar_manifest(str(p), m)
    result, ok = read_sidecar_manifest(str(p))
    assert ok is True
    assert result == m


def test_write_sidecar_manifest_overwrites_previous_content(tmp_path):
    p = tmp_path / "mod.py"
    write_sidecar_manifest(
        str(p),
        {"version": 1, "tested_at": "x", "module_hash": "old", "functions": []},
    )
    write_sidecar_manifest(
        str(p),
        {"version": 1, "tested_at": "x", "module_hash": "new", "functions": []},
    )
    result, _ = read_sidecar_manifest(str(p))
    assert result["module_hash"] == "new"


def test_write_sidecar_manifest_uses_source_path_plus_suffix(tmp_path):
    p = tmp_path / "mod.py"
    write_sidecar_manifest(
        str(p),
        {"version": 1, "tested_at": "x", "module_hash": "abc", "functions": []},
    )
    assert (tmp_path / "mod.py.manifest.json").is_file()


def test_write_sidecar_manifest_does_not_touch_other_files_sidecars(tmp_path):
    p_a = tmp_path / "a.py"
    p_b = tmp_path / "b.py"
    write_sidecar_manifest(
        str(p_a),
        {"version": 1, "tested_at": "x", "module_hash": "a-hash", "functions": []},
    )
    write_sidecar_manifest(
        str(p_b),
        {"version": 1, "tested_at": "x", "module_hash": "b-hash", "functions": []},
    )
    result_a, ok_a = read_sidecar_manifest(str(p_a))
    result_b, ok_b = read_sidecar_manifest(str(p_b))
    assert ok_a is True
    assert ok_b is True
    assert result_a["module_hash"] == "a-hash"
    assert result_b["module_hash"] == "b-hash"


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
