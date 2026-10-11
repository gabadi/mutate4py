"""Idempotence of a scored run (ADR 0006): an identical rerun rewrites nothing."""

import io
import json
from contextlib import redirect_stdout

import pytest

from ._pytest_project_helpers import write_always_passing_pytest_project
from mutate4py._discovery import discover_sites
from mutate4py._runner import RunMutationsRequest, run_mutations

OLD_TESTED_AT = "2020-01-01T00:00:00Z"


def _write_lcov(path: str, source_abs: str, covered_lines: list[int]) -> None:
    da_lines = "\n".join(f"DA:{ln},1" for ln in covered_lines)
    with open(path, "w") as f:
        f.write(f"SF:{source_abs}\n{da_lines}\nend_of_record\n")


def _scored_run(src_path: str, source: str, lcov_path: str, pytest_args: list[str], cwd: str) -> tuple[int, str]:
    request = RunMutationsRequest(
        path=src_path,
        source=source,
        cov_cmd=None,
        lcov_path=lcov_path,
        reuse_coverage=False,
        pytest_args=pytest_args,
        timeout_factor=10,
        lines_filter=None,
        since_last_run=False,
        mutate_all=True,
        warning_threshold=1000,
        cwd=cwd,
    )
    with redirect_stdout(io.StringIO()):
        code = run_mutations(request)
    with open(src_path) as f:
        return code, f.read()


def _tested_at(content: str) -> str:
    manifest_line = [ln for ln in content.splitlines() if ln.startswith("# {")][0]
    return json.loads(manifest_line[2:])["tested_at"]


@pytest.mark.component
def test_scored_rerun_with_identical_results_leaves_manifest_unchanged(tmp_path):
    """The mutant `a > b -> a >= b` survives the always-passing tests, so the
    function keeps a recorded survivor and is rescored on every run. The
    second run must still leave tested_at and the manifest bytes untouched.

    The first run's tested_at is replaced with an old value before the second
    run, so a rewrite shows up even when both runs land in the same second."""
    src = "def f(a, b):\n    return a > b\n"
    src_path = str(tmp_path / "calc.py")
    lcov_path = str(tmp_path / "cov.lcov")
    with open(src_path, "w") as f:
        f.write(src)
    _write_lcov(lcov_path, src_path, [s.line for s in discover_sites(src)])
    pytest_args = write_always_passing_pytest_project(str(tmp_path))

    first_code, first = _scored_run(src_path, src, lcov_path, pytest_args, str(tmp_path))
    seeded = first.replace(_tested_at(first), OLD_TESTED_AT)
    second_code, second = _scored_run(src_path, seeded, lcov_path, pytest_args, str(tmp_path))

    assert first_code == 3
    assert second_code == 3
    assert _tested_at(second) == OLD_TESTED_AT
    assert second == seeded
