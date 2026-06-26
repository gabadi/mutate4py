"""LCOV coverage acquisition and line-gate partitioning for mutate4py."""

import os
import subprocess

from mutate4py._discovery import Site

DEFAULT_LCOV_PATH = "coverage.lcov"


class CoverageError(Exception):
    """Raised when coverage acquisition fails (missing file, command error)."""


def _paths_match_by_suffix(sf_path: str, source_path: str) -> bool:
    """Return True if one path is a path-suffix of the other."""
    a = sf_path.replace("\\", "/")
    b = source_path.replace("\\", "/")
    return a.endswith(b) or b.endswith(a)


def parse_lcov(lcov_text: str, source_path: str) -> set[int]:
    """Parse LCOV text and return covered line numbers for source_path.

    A line is covered iff it has a DA:<line>,<count> record with count > 0.
    BRDA records are ignored. SF path matching is suffix-based.
    """
    covered: set[int] = set()
    in_matching_file = False
    for raw_line in lcov_text.splitlines():
        line = raw_line.strip()
        if line.startswith("SF:"):
            sf_path = line[3:]
            in_matching_file = _paths_match_by_suffix(sf_path, source_path)
        elif line == "end_of_record":
            in_matching_file = False
        elif in_matching_file and line.startswith("DA:"):
            parts = line[3:].split(",", 1)
            if len(parts) == 2:
                try:
                    lineno = int(parts[0])
                    count = int(parts[1])
                    if count > 0:
                        covered.add(lineno)
                except ValueError:
                    pass
        # BRDA records are intentionally ignored (ADR 0007)
    return covered


def partition_sites(sites: list[Site], covered_lines: set[int]) -> tuple[int, int]:
    """Return (covered_count, uncovered_count) for the given sites."""
    covered = sum(1 for s in sites if s.line in covered_lines)
    return covered, len(sites) - covered


def acquire_coverage(
    *,
    cov_cmd: str | None,
    lcov_path: str | None,
    reuse: bool,
    cwd: str,
    source_path: str,
) -> set[int]:
    """Acquire LCOV coverage and return covered line numbers.

    Exactly one of cov_cmd, lcov_path, or reuse must be active.
    Raises CoverageError if the coverage source is missing or unusable.
    """
    if cov_cmd is not None:
        result = subprocess.run(cov_cmd, shell=True, cwd=cwd)
        if result.returncode != 0:
            raise CoverageError(
                f"Coverage command failed (exit {result.returncode}): {cov_cmd}"
            )
        # After running, read from coverage.lcov in cwd (ADR 0007)
        effective_path = os.path.join(cwd, DEFAULT_LCOV_PATH)
        if not os.path.isfile(effective_path):
            raise CoverageError(
                f"Coverage command did not produce {DEFAULT_LCOV_PATH}. "
                "Ensure your --cov-cmd writes LCOV to coverage.lcov."
            )
        with open(effective_path) as f:
            return parse_lcov(f.read(), source_path)

    if lcov_path is not None:
        if not os.path.isfile(lcov_path):
            raise CoverageError(
                f"LCOV file not found: {lcov_path}. "
                "Generate coverage first then supply the path."
            )
        with open(lcov_path) as f:
            return parse_lcov(f.read(), source_path)

    # reuse=True
    effective_path = os.path.join(cwd, DEFAULT_LCOV_PATH)
    if not os.path.isfile(effective_path):
        raise CoverageError(
            f"No coverage file at {effective_path}. "
            "Run your coverage tool once (e.g. 'coverage lcov') to generate it."
        )
    with open(effective_path) as f:
        return parse_lcov(f.read(), source_path)
