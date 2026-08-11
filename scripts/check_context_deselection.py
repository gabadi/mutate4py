"""Gate: no test recorded as a named context in `.coverage` may be deselected
by the `mutate` recipe's --pytest-args (justfile).

If it is, narrowing can still pick that test's node ID for some Mutant Site;
the mutation run's marker filter then deselects it, pytest exits 5 ("no tests
collected") or 4 (usage error), and `_cmd.py`'s `classify_exit_code` (#55)
now raises `NoTestsCollectedError` rather than scoring the Mutant `killed` --
so this is no longer a silent misscore, but it still aborts the whole
mutation run mid-batch over a misconfiguration this gate can catch ahead of
time, at `just check` time instead. See issue #54.
"""

from __future__ import annotations

import argparse
import logging
import shlex
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

from mutate4py._test_selection import _strip_context_suffix

# scripts/ sits outside src/mutate4py/, so tach.toml layering doesn't cover this
# import -- an intentional, unchecked coupling to a private helper. Reusing it
# (rather than duplicating the context->node-id parsing) keeps this script's
# notion of a "node ID" identical to the one _test_selection.py already uses
# for per-Mutant narrowing.
_logger = logging.getLogger("mutate4py.check_context_deselection")

__all__ = [
    "GateError",
    "Violation",
    "check",
    "collect_node_ids",
    "files_for_context_ids",
    "main",
    "named_contexts",
]

DEFAULT_PYTEST_ARGS = "-p no:tach -m 'not integration'"
DEFAULT_INTEGRATION_PYTEST_ARGS = "-m integration"


class GateError(Exception):
    """Raised when the gate cannot determine violations (missing/partial .coverage)."""


class Violation(NamedTuple):
    node_id: str
    files: list[str]


def named_contexts(db_path: Path) -> dict[str, int]:
    """Map pytest node ID -> context id for every named context in db_path."""
    db_path = Path(db_path)
    if not db_path.exists():
        raise GateError(f"{db_path} does not exist; run `just check test-unit test-integration` first.")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, context FROM context WHERE context != ''")
        result: dict[str, int] = {}
        for context_id, context in cur.fetchall():
            result[_strip_context_suffix(context)] = context_id
        return result
    finally:
        conn.close()


def collect_node_ids(pytest_args: list[str], cwd: Path) -> list[str]:
    """Run `pytest --collect-only -q <pytest_args>`; return collected node IDs.

    Node ID lines are unindented and contain "::"; everything else pytest
    prints during collection (warnings, the summary line) is either indented
    or lacks "::" in the same position.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *pytest_args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1, 5):
        raise GateError(f"pytest --collect-only {pytest_args} failed:\n{result.stdout}\n{result.stderr}")
    node_ids = []
    for line in result.stdout.splitlines():
        if not line or line[0].isspace():
            continue
        if "::" not in line:
            continue
        node_ids.append(line.strip())
    return node_ids


def files_for_context_ids(db_path: Path, context_ids: list[int]) -> list[str]:
    """Distinct file paths touched by any arc recorded under context_ids."""
    conn = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        placeholders = ",".join("?" * len(context_ids))
        cur.execute(
            f"SELECT DISTINCT f.path FROM arc a JOIN file f ON f.id = a.file_id WHERE a.context_id IN ({placeholders})",
            context_ids,
        )
        return sorted(path for (path,) in cur.fetchall())
    finally:
        conn.close()


def check(db_path: Path, not_integration_args: list[str], integration_args: list[str], cwd: Path) -> list[Violation]:
    """Return every named context deselected by not_integration_args, or raise GateError."""
    contexts = named_contexts(db_path)
    selected = set(collect_node_ids(not_integration_args, cwd))
    integration_collected = set(collect_node_ids(integration_args, cwd))

    if integration_collected and not (integration_collected & contexts.keys()):
        raise GateError(
            f"{db_path} has no named context for any of the {len(integration_collected)} "
            "collected integration test(s); looks like only the unit half was recorded. "
            "Run `just check test-unit test-integration`."
        )
    if selected and not (selected & contexts.keys()):
        raise GateError(
            f"{db_path} has no named context for any of the {len(selected)} collected "
            "non-integration test(s); looks like only the integration half was recorded. "
            "Run `just check test-unit test-integration`."
        )

    violations = []
    for node_id in sorted(contexts):
        if node_id in selected:
            continue
        files = files_for_context_ids(db_path, [contexts[node_id]])
        violations.append(Violation(node_id, files))
    return violations


def _relativize(paths: list[str], repo_root: Path) -> list[str]:
    relativized = []
    for path in paths:
        try:
            relativized.append(str(Path(path).relative_to(repo_root)))
        except ValueError:
            relativized.append(path)
    return relativized


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage-db", default=".coverage", type=Path)
    parser.add_argument(
        "--pytest-args",
        default=DEFAULT_PYTEST_ARGS,
        help="Same value as the `mutate` recipe's --pytest-args (justfile).",
    )
    parser.add_argument("--integration-pytest-args", default=DEFAULT_INTEGRATION_PYTEST_ARGS)
    parser.add_argument("--cwd", default=Path.cwd(), type=Path)
    args = parser.parse_args(argv)

    try:
        violations = check(
            args.coverage_db,
            shlex.split(args.pytest_args),
            shlex.split(args.integration_pytest_args),
            args.cwd,
        )
    except GateError as exc:
        _logger.error(f"error: {exc}")
        return 1

    if not violations:
        _logger.info(
            f"no context-deselection violations ({len(named_contexts(args.coverage_db))} named contexts checked)"
        )
        return 0

    _logger.error(
        f"{len(violations)} test(s) with a named .coverage context are deselected by "
        f"--pytest-args {args.pytest_args!r}:"
    )
    for node_id, files in violations:
        rel_files = ", ".join(_relativize(files, args.cwd))
        _logger.error(f"  {node_id}\n    loses narrowing for: {rel_files}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
