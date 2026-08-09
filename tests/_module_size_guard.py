"""Module size guard: hand-rolled, not delegated to a linter.

Ruff has no file-length rule and has declined to add one — the upstream
Pylint `too-many-lines` tracking issue is marked out of scope as
formatter-incompatible, and a complete implementation was submitted and
closed unmerged. No linter anywhere counts top-level definitions per
module. The existing gates (crap, coverage, dry) are all scoped below the
file, so nothing stops a module from growing to hundreds of lines and dozens
of definitions with every other gate green. Do not "simplify" this away by
reaching for a ruff rule that does not exist.

Two axes (physical lines, top-level definitions) and a two-way ratchet:
a file already over cap gets an exemption entry recording its current
measured values. It may never exceed that entry, and when it shrinks the
entry must be lowered in the same change — so a file cannot shrink and then
silently regrow to a stale high-water mark.
"""

import ast
from dataclasses import dataclass
from pathlib import Path

_DEF_NODE_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


@dataclass(frozen=True)
class Caps:
    max_lines: int
    max_defs: int


@dataclass(frozen=True)
class ExemptionEntry:
    lines: int
    defs: int


def count_lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def count_top_level_defs(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return sum(1 for node in tree.body if isinstance(node, _DEF_NODE_TYPES))


def measure(path: Path) -> tuple[int, int]:
    return count_lines(path), count_top_level_defs(path)


def check_file(
    rel_path: str,
    path: Path,
    caps: Caps,
    exemptions: dict[str, ExemptionEntry],
) -> str | None:
    """Return a violation message for path, or None if it is clean.

    rel_path is the key into exemptions (a project-relative, '/'-joined
    path) and doubles as the name printed in violation messages.
    """
    lines, defs = measure(path)
    entry = exemptions.get(rel_path)

    if entry is None:
        if lines <= caps.max_lines and defs <= caps.max_defs:
            return None
        return (
            f"{rel_path}: lines={lines}, defs={defs} exceeds the cap "
            f"(lines<={caps.max_lines}, defs<={caps.max_defs}) with no "
            "exemption entry — add one recording these values, or shrink "
            "the file"
        )

    if lines > entry.lines or defs > entry.defs:
        return (
            f"{rel_path}: lines={lines}, defs={defs} exceeds its exemption "
            f"entry (lines={entry.lines}, defs={entry.defs}) — shrink the "
            "file, or raise the entry if the growth is intentional"
        )

    if lines < entry.lines or defs < entry.defs:
        return (
            f"{rel_path}: lines={lines}, defs={defs} is below its "
            f"exemption entry (lines={entry.lines}, defs={entry.defs}) — "
            f"lower the entry to record lines={lines}, defs={defs}, or "
            "delete it if the file now fits under the cap"
        )

    return None


def check_files(
    files: dict[str, Path],
    caps: Caps,
    exemptions: dict[str, ExemptionEntry],
) -> list[str]:
    """Check every (rel_path -> path) pair, aggregating all violations."""
    violations = []
    for rel_path, path in files.items():
        violation = check_file(rel_path, path, caps, exemptions)
        if violation is not None:
            violations.append(violation)
    return violations
