"""LCOV coverage acquisition for mutate4py."""

import os
import subprocess

DEFAULT_LCOV_PATH = "coverage.lcov"


class CoverageError(Exception):
    """Raised when coverage acquisition fails (missing file, command error)."""


def _paths_match_by_suffix(sf_path: str, source_path: str) -> bool:
    """Return True if one path is a path-suffix of the other."""
    a = sf_path.replace("\\", "/")
    b = source_path.replace("\\", "/")
    return a.endswith(b) or b.endswith(a)


def _parse_da_line(line: str) -> int | None:
    """Return the covered line number from a DA record, or None if uncovered/invalid."""
    parts = line[3:].split(",", 1)
    if len(parts) != 2:
        return None
    try:
        lineno = int(parts[0])
        count = int(parts[1])
        return lineno if count > 0 else None
    except ValueError:
        return None


def _update_lcov_state(
    line: str,
    in_matching_file: bool,
    source_path: str,
    covered: set[int],
) -> bool:
    """Process one LCOV line; return updated in_matching_file flag."""
    if line.startswith("SF:"):
        return _paths_match_by_suffix(line[3:], source_path)
    if line == "end_of_record":
        return False
    if in_matching_file and line.startswith("DA:"):
        lineno = _parse_da_line(line)
        if lineno is not None:
            covered.add(lineno)
    # BRDA records are intentionally ignored (ADR 0007)
    return in_matching_file


def parse_lcov(lcov_text: str, source_path: str) -> set[int]:
    """Parse LCOV text and return covered line numbers for source_path.

    A line is covered iff it has a DA:<line>,<count> record with count > 0.
    BRDA records are ignored. SF path matching is suffix-based.
    """
    covered: set[int] = set()
    in_matching_file = False
    for raw_line in lcov_text.splitlines():
        in_matching_file = _update_lcov_state(
            raw_line.strip(), in_matching_file, source_path, covered
        )
    return covered


def _read_lcov_file(path: str, source_path: str) -> set[int]:
    """Read and parse an LCOV file; raise CoverageError if missing."""
    if not os.path.isfile(path):
        raise CoverageError(
            f"LCOV file not found: {path}. "
            "Generate coverage first then supply the path."
        )
    with open(path) as f:
        return parse_lcov(f.read(), source_path)


def _resolve_lcov_path(
    cov_cmd: str | None,
    lcov_path: str | None,
    reuse: bool,
    cwd: str,
) -> str:
    """Return the LCOV file path to read, running cov_cmd first if needed."""
    if cov_cmd is not None:
        result = subprocess.run(cov_cmd, shell=True, cwd=cwd)
        if result.returncode != 0:
            raise CoverageError(
                f"Coverage command failed (exit {result.returncode}): {cov_cmd}"
            )
        default = os.path.join(cwd, DEFAULT_LCOV_PATH)
        if not os.path.isfile(default):
            raise CoverageError(
                f"Coverage command did not produce {DEFAULT_LCOV_PATH}. "
                "Ensure your --cov-cmd writes LCOV to coverage.lcov."
            )
        return default
    if lcov_path is not None:
        return lcov_path
    # reuse=True
    return os.path.join(cwd, DEFAULT_LCOV_PATH)


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
    path = _resolve_lcov_path(cov_cmd, lcov_path, reuse, cwd)
    return _read_lcov_file(path, source_path)
