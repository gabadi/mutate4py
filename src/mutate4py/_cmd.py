"""Low-level argv runner shared by every mutant-execution path: runs an
already-built argument list directly, no shell.
"""

import subprocess

__all__ = ["run_argv"]


def run_argv(argv: list[str], cwd: str, timeout: float) -> str:
    """Run argv with no shell; return the classification: killed, timeout, or survived.

    A shell's "command not found" is a graceful nonzero exit; without a shell
    the same condition raises OSError (e.g. argv[0] unresolvable on PATH),
    which is mapped back to "killed" rather than left to crash the run.
    """
    try:
        result = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "timeout"
    except OSError:
        return "killed"
    return "survived" if result.returncode == 0 else "killed"
