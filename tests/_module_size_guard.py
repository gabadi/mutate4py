"""Module size guard: hand-rolled, not delegated to a linter.

Ruff has no file-length rule and has declined to add one — the upstream
Pylint `too-many-lines` tracking issue is marked out of scope as
formatter-incompatible, and a complete implementation was submitted and
closed unmerged. No linter anywhere counts top-level definitions per
module. The existing gates (crap, coverage, dry) are all scoped below the
file, so nothing stops a module from growing to hundreds of lines and dozens
of definitions with every other gate green. Do not "simplify" this away by
reaching for a ruff rule that does not exist.

Two axes (physical lines, top-level definitions), one flat cap per axis,
no per-file escape hatch. An earlier version of this guard (issue #38)
ratcheted an exemption entry per over-cap file instead of enforcing the
flat cap directly — that ratchet made raising a number in a committed
table the cheapest green move for a growing file, cheaper than the
extraction it was meant to force. Every file now measures against the
flat cap only; if a file grows past it, shrink the file.
"""

import ast
from dataclasses import dataclass
from pathlib import Path

_DEF_NODE_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


@dataclass(frozen=True)
class Caps:
    max_lines: int
    max_defs: int


def count_lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def count_top_level_defs(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return sum(1 for node in tree.body if isinstance(node, _DEF_NODE_TYPES))


def measure(path: Path) -> tuple[int, int]:
    return count_lines(path), count_top_level_defs(path)


def check_file(rel_path: str, path: Path, caps: Caps) -> str | None:
    """Return a violation message for path, or None if it is clean.

    rel_path is the name printed in violation messages.
    """
    lines, defs = measure(path)
    if lines <= caps.max_lines and defs <= caps.max_defs:
        return None
    return f"{rel_path}: lines={lines}, defs={defs} exceeds the cap (lines<={caps.max_lines}, defs<={caps.max_defs})"


def check_files(files: dict[str, Path], caps: Caps) -> list[str]:
    """Check every (rel_path -> path) pair, aggregating all violations."""
    violations = []
    for rel_path, path in files.items():
        violation = check_file(rel_path, path, caps)
        if violation is not None:
            violations.append(violation)
    return violations
