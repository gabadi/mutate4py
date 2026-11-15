"""Low-level argv runner shared by every mutant-execution path: runs an
already-built argument list directly, no shell.
"""

import subprocess
from collections.abc import Mapping

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
    """Classify a pytest process's exit code: survived (0), killed (1), an abort
    status (no-tests-collected, usage-error) meaning no test ran at all, or errored.

    Only exit 0 and exit 1 show that pytest ran tests. Any other code (2 interrupted,
    3 internal error, a code a shell or a forked child leaves) is "errored": it shows
    nothing about the tests, so a Control run it ends clears no argv (ADR 0018).
    For a Mutant, `errored` still counts as killed (ADR 0011).
    """
    if returncode == 0:
        return "survived"
    if returncode == 1:
        return "killed"
    return _ABORT_EXIT_CODES.get(returncode, "errored")


def run_argv(argv: list[str], cwd: str, timeout: float, env: Mapping[str, str] | None = None) -> str:
    """Run argv with no shell; return the classification: survived, killed, errored,
    timeout, or an abort status (no-tests-collected, usage-error).

    A shell's "command not found" is a graceful nonzero exit; without a shell
    the same condition raises OSError (e.g. argv[0] unresolvable on PATH),
    which is mapped to "errored" rather than left to crash the run: no pytest
    ran, so no test did.
    """
    try:
        result = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return "timeout"
    except OSError:
        return "errored"
    return classify_exit_code(result.returncode)
