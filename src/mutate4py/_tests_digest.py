"""Per-function tests digest: the test-side inputs a function's score depends on."""

import hashlib
import json
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

__all__ = ["DigestInputs", "FunctionUnit", "function_digest"]


@dataclass(frozen=True)
class DigestInputs:
    """Plain run-level inputs to function_digest, built by the Measurement."""

    rootdir: Path
    reach: Mapping[str, Mapping[int, frozenset[str]]]
    all_test_files: frozenset[str]
    conftests_for: Mapping[str, tuple[str, ...]]
    support_files: frozenset[str]


@dataclass(frozen=True)
class FunctionUnit:
    """The function whose digest is computed: its source path and FunctionID."""

    path: str
    function_id: str


def _content_sha(rootdir: Path, relpath: str) -> str:
    """SHA-256 of a file's bytes, except pyproject.toml: only its [tool.pytest] table counts.

    Edits to [project] or other tools' tables cannot change a pytest run, so they must not
    invalidate every function's digest.
    """
    path = rootdir / relpath
    if path.name != "pyproject.toml":
        return hashlib.sha256(path.read_bytes()).hexdigest()
    pytest_table = tomllib.loads(path.read_text(encoding="utf-8")).get("tool", {}).get("pytest")
    return hashlib.sha256(json.dumps(pytest_table, sort_keys=True, default=str).encode()).hexdigest()


def _reaching_tests(
    inputs: DigestInputs,
    unit: FunctionUnit,
    site_lines: frozenset[int],
    static_lines: frozenset[int],
) -> set[str]:
    """Test files that reach the unit's covered Site lines, or every collected test file when one is static."""
    if static_lines:
        return set(inputs.all_test_files)
    by_line = inputs.reach.get(unit.path, {})
    return {t for line in site_lines for t in by_line.get(line, frozenset())}


def function_digest(
    inputs: DigestInputs,
    unit: FunctionUnit,
    site_lines: frozenset[int],
    static_lines: frozenset[int],
) -> str:
    """SHA-256 over sorted (relpath, content SHA-256) pairs for one function."""
    tests = _reaching_tests(inputs, unit, site_lines, static_lines)
    conftests = {c for t in tests for c in inputs.conftests_for[t]}
    relpaths = tests | conftests | inputs.support_files
    pairs = sorted((rel, _content_sha(inputs.rootdir, rel)) for rel in relpaths)
    return hashlib.sha256(json.dumps(pairs, separators=(",", ":")).encode()).hexdigest()
