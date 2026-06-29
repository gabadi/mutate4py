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


# mutate4py-manifest-begin
# {"version":1,"tested_at":"2026-06-29T00:35:57Z","module_hash":"fc574760f8d4d11331c022c3028560d15c36ab152528f0f37aeb28de062cf0e2","functions":[{"id":"func/_paths_match_by_suffix","name":"_paths_match_by_suffix","line":13,"end_line":17,"hash":"210c94a33f6d3064f26a99b45dafb7791fcfda847794f2d9e56aaf2dcd819b7c"},{"id":"func/_parse_da_line","name":"_parse_da_line","line":20,"end_line":30,"hash":"9eb384b1acaf86f3425bcdd38ba55b75eadc8b20e3872b3b7122656365a23047"},{"id":"func/_update_lcov_state","name":"_update_lcov_state","line":33,"end_line":49,"hash":"705c78063adcb2e19d37f4e7c835902c7d996bfe4e090d4ea372507c2a998472"},{"id":"func/parse_lcov","name":"parse_lcov","line":52,"end_line":64,"hash":"22d4f67b83ea2dd5a74ebc72a0eae43614943539f36f5c521ef2b687ab8a57d4"},{"id":"func/_read_lcov_file","name":"_read_lcov_file","line":67,"end_line":75,"hash":"0a15b57b4dd78d99f3688208cb4fcf1ef7b2d7754a42bf29623e57a3733177a3"},{"id":"func/_resolve_lcov_path","name":"_resolve_lcov_path","line":78,"end_line":101,"hash":"2c428d5975bf6c07bcd484c463cf91d9eb7307c65159722a61718c7b57bd9534"},{"id":"func/acquire_coverage","name":"acquire_coverage","line":104,"end_line":118,"hash":"353972aec9efc12b952369883ee7f52375b5cb19f3711c8cd817249b3c8520fa"}]}
# mutate4py-manifest-end
