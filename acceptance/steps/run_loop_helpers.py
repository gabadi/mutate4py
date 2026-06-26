"""Shared helpers for run-loop acceptance step handlers."""

import os
import subprocess

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))


def make_source_with_compare_on_line(target_lines: list[int]) -> str:
    """Generate a Python source file with Compare sites on target_lines.

    Each target line gets a comparison expression in a function.
    Lines 1..max are filled so that target_lines have mutable sites.
    """
    max_line = max(target_lines) if target_lines else 1
    lines = []
    fn_counter = [0]

    def fn_for_line(ln: int) -> str:
        fn_counter[0] += 1
        return f"func_{fn_counter[0]}"

    # Build source: pad to have comparison on each target line
    # Strategy: one function per target line site
    # We'll build functions that start just before each target line
    src_lines: list[str] = [""] * (max_line + 2)

    fn_idx = 0
    for target in sorted(target_lines):
        fn_idx += 1
        fn_name = f"f{fn_idx}"
        # Place def on target-1, comparison on target
        def_line = target - 1
        if def_line < 1:
            def_line = 1
        # We need target to be the comparison line
        # Simple: put function on target-1, return on target
        if def_line > 0 and def_line < target:
            src_lines[def_line] = f"def {fn_name}(a, b):"
            src_lines[target] = f"    return a > b"

    # Fill empty lines with pass statements
    in_fn = False
    result = []
    for i in range(1, max_line + 2):
        line = src_lines[i]
        if not line:
            if in_fn:
                result.append("    pass")
            else:
                result.append("")
        else:
            result.append(line)
            in_fn = line.startswith("def ")

    return "\n".join(result) + "\n"


def make_lcov(source_abs: str, covered_lines: list[int]) -> str:
    """Build LCOV text marking the given lines covered for source_abs."""
    da_lines = "\n".join(f"DA:{ln},1" for ln in sorted(covered_lines))
    return f"SF:{source_abs}\n{da_lines}\nend_of_record\n"


def write_pass_script(path: str) -> None:
    """Write a shell script that always exits 0."""
    with open(path, "w") as f:
        f.write("#!/bin/sh\nexit 0\n")
    os.chmod(path, 0o755)


def write_fail_script(path: str) -> None:
    """Write a shell script that always exits 1."""
    with open(path, "w") as f:
        f.write("#!/bin/sh\nexit 1\n")
    os.chmod(path, 0o755)


def run_mutate4py(cwd: str, *args: str) -> subprocess.CompletedProcess:
    """Run mutate4py via uv in the given cwd."""
    return subprocess.run(
        ["uv", "run", "mutate4py"] + list(args),
        capture_output=True,
        text=True,
        cwd=cwd,
    )
