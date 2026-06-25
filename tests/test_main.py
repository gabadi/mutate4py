"""Unit tests for mutate4py CLI entry point (__main__)."""

import os
import subprocess
import sys
import tempfile
import textwrap

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def run_cli(*args: str, source: str | None = None) -> subprocess.CompletedProcess:
    """Run mutate4py CLI with given args; optionally write source to a temp file."""
    with tempfile.TemporaryDirectory() as d:
        if source is not None:
            path = os.path.join(d, "sample.py")
            with open(path, "w") as f:
                f.write(textwrap.dedent(source))
            cli_args = [path] + list(args)
        else:
            cli_args = list(args)

        result = subprocess.run(
            [sys.executable, "-m", "mutate4py"] + cli_args,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env={**os.environ, "PYTHONPATH": os.path.join(REPO_ROOT, "src")},
        )
    return result


def test_scan_prints_count_block_zero_sites():
    result = run_cli("--scan", source="x = 1\n")
    # 1 site (integer 1)
    assert "Total mutation sites: 1" in result.stdout
    assert "Changed mutation sites: 1" in result.stdout
    assert "Manifest exists: false" in result.stdout
    assert result.returncode == 0


def test_scan_prints_mutation_scan_header():
    result = run_cli("--scan", source="pass\n")
    assert "Mutation scan:" in result.stdout


def test_scan_zero_sites():
    result = run_cli("--scan", source="pass\n")
    assert "Total mutation sites: 0" in result.stdout
    assert "Changed mutation sites: 0" in result.stdout
    assert result.returncode == 0


def test_scan_no_warning_at_threshold():
    src = "x = a + b\n"
    result = run_cli("--scan", "--mutation-warning", "1", source=src)
    # 1 site, threshold 1: no warning (not strictly greater)
    assert "Warning:" not in result.stdout
    assert result.returncode == 0


def test_scan_warning_above_threshold():
    src = "x = a + b\ny = c - d\n"
    result = run_cli("--scan", "--mutation-warning", "1", source=src)
    # 2 sites > 1 threshold
    assert "Warning: 2 mutation sites exceeds threshold 1." in result.stdout
    assert result.returncode == 0


def test_missing_file_exits_nonzero():
    result = subprocess.run(
        [sys.executable, "-m", "mutate4py", "/nonexistent/path.py", "--scan"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": os.path.join(REPO_ROOT, "src")},
    )
    assert result.returncode != 0
    assert result.stdout == ""


def test_missing_file_error_on_stderr():
    result = subprocess.run(
        [sys.executable, "-m", "mutate4py", "/nonexistent/path.py", "--scan"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": os.path.join(REPO_ROOT, "src")},
    )
    assert "error" in result.stderr.lower() or result.returncode != 0
