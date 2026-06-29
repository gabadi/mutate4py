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
# {"version":1,"tested_at":"2026-06-29T00:53:58Z","module_hash":"8c08d73e49378ffd9c0591a6efaf943a26980cd80252f1fa0a044f24a6e053fd","functions":[{"id":"func/_paths_match_by_suffix","name":"_paths_match_by_suffix","line":13,"end_line":17,"hash":"3e7c26ffc86bedd683984a0188d901a1088a13dace7203f7475691d0d7794387"},{"id":"func/_parse_da_line","name":"_parse_da_line","line":20,"end_line":30,"hash":"d58a127b74f15e77899e88e711a292ed72f3aff712cebc7a35b1009a943b8702"},{"id":"func/_update_lcov_state","name":"_update_lcov_state","line":33,"end_line":49,"hash":"c6f2d23ead6d169c458169902c8d7ce8a1e1b4abec2cc0b89d2d122a9a9d95a0"},{"id":"func/parse_lcov","name":"parse_lcov","line":52,"end_line":64,"hash":"1a9c731e0e5cc7b106c67ac6b2f81d1259e3be74483caa045d4a326e153f44b4"},{"id":"func/_read_lcov_file","name":"_read_lcov_file","line":67,"end_line":75,"hash":"30d6ebd781e8e44de0b47b8df8ab3a0a78d5f5cc4832d41264efe1d8fd6e18b1"},{"id":"func/_resolve_lcov_path","name":"_resolve_lcov_path","line":78,"end_line":101,"hash":"92a6674f50d43b3a4dc9f75ffadc10d66cf5f48b746506b903e0553493bffdb6"},{"id":"func/acquire_coverage","name":"acquire_coverage","line":104,"end_line":118,"hash":"6fc5ddabdf24e748c8dbea80c53b50cf428204a467483af1e61822abf17bbec2"}]}
# mutate4py-manifest-end
