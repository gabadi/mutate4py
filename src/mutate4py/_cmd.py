"""Low-level argv runner shared by every mutant-execution path: runs an
already-built argument list directly, no shell.
"""

import subprocess

__all__ = ["classify_exit_code", "run_argv"]

# pytest exit codes meaning it exercised no test at all for this Mutant: 5 is
# "no tests were collected" (a narrowed/static selection or a --pytest-args
# filter matched nothing), 4 is "usage error" (pytest never reached collection
# at all — e.g. a malformed --pytest-args, or a narrowed node ID pytest can't
# even parse as a path). Both are the same defect one step later than ADR
# 0018's line-absent/file-absent case: nothing ran, so scoring the Mutant
# `killed` would be a silent false win (issue #55).
_ABORT_EXIT_CODES = {
    4: "usage-error",
    5: "no-tests-collected",
}


def classify_exit_code(returncode: int) -> str:
    """Classify a pytest process's exit code: survived, killed, or an abort
    status (no-tests-collected, usage-error) meaning no test ran at all."""
    if returncode == 0:
        return "survived"
    return _ABORT_EXIT_CODES.get(returncode, "killed")


def run_argv(argv: list[str], cwd: str, timeout: float) -> str:
    """Run argv with no shell; return the classification: killed, timeout,
    survived, or an abort status (no-tests-collected, usage-error).

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
    return classify_exit_code(result.returncode)
