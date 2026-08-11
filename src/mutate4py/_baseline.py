"""Baseline timing and per-Mutant overhead measurement.

No cross-module deps: both the timed Baseline run and the extra
`--collect-only` overhead probe build their own argv and shell out directly.
See `run_baseline`'s own docstring for why it never imports
`_subprocess_executor`'s argv helper.
"""

import subprocess
import sys
import time

__all__ = [
    "measure_per_mutant_overhead",
    "resolve_baseline_and_overhead",
    "run_baseline",
]


def _baseline_reason(result: subprocess.CompletedProcess) -> str:
    stderr = (result.stderr or b"").decode(errors="replace").strip()
    if stderr:
        return stderr.splitlines()[0]
    return f"exit code {result.returncode}"


def _timed_pytest_run(args: list[str], cwd: str) -> tuple[float, subprocess.CompletedProcess]:
    """Run `sys.executable -m pytest <args>`, no shell, timed; return
    (duration_seconds, result).

    Shared by `run_baseline` and `measure_per_mutant_overhead`: both time a
    `sys.executable -m pytest` subprocess — the same interpreter's pytest
    the executors run mutants against — and build the argv inline rather
    than importing mutate4py._subprocess_executor's helper, since both run
    before executor preparation and an import here would run unconditionally
    on every mutation run, poisoning the forking executor's module-leak
    check whenever the scan target is _cmd.py or _subprocess_executor.py
    itself (the hazard the lazy imports elsewhere in this codebase, see
    _executor_selection.py, exist to avoid).
    """
    start = time.monotonic()
    result = subprocess.run([sys.executable, "-m", "pytest", *args], cwd=cwd, capture_output=True)
    return time.monotonic() - start, result


def run_baseline(pytest_args: list[str], cwd: str) -> tuple[float, str | None]:
    """Run baseline; return (duration_seconds, error_reason_or_None)."""
    elapsed, result = _timed_pytest_run(pytest_args, cwd)
    if result.returncode != 0:
        return elapsed, _baseline_reason(result)
    return elapsed, None


def measure_per_mutant_overhead(mutant_pytest_args: list[str], cwd: str) -> float:
    """One extra collect-only pass, timed: the fixed cost every Mutant
    invocation pays regardless of what its tests do.

    Runs with mutant_pytest_args — the same (neutralised) argument list a
    Mutant run gets — so the measurement reflects what's left after
    disabling coverage/benchmark, not the Baseline's own pre-neutralisation
    cost. `--collect-only` means no test body ever runs, but pytest's own
    bootstrap and any remaining session-scope plugin hooks (unknown plugins,
    deliberately untouched) still fire, which is exactly the cost this
    isolates. The exit code is not inspected: this is a timing probe, not a
    correctness gate — the real Baseline already gates correctness.
    """
    elapsed, _ = _timed_pytest_run(["--collect-only", "-q", *mutant_pytest_args], cwd)
    return elapsed


def resolve_baseline_and_overhead(
    pytest_args: list[str],
    cwd: str,
    mutant_pytest_args: list[str],
    pre_supplied_baseline_duration: float | None,
) -> tuple[float | None, str | None, float | None]:
    """Return (baseline_duration, error, overhead_duration).

    A pre-supplied baseline_duration is passed through untouched and skips
    the overhead measurement too: there is no freshly-run Baseline to attach
    the "one extra collect-only pass" to, and this is also the seam tests
    use to avoid a real subprocess/fork entirely.
    """
    if pre_supplied_baseline_duration is not None:
        return pre_supplied_baseline_duration, None, None
    duration, error = run_baseline(pytest_args, cwd)
    if error is not None:
        return duration, error, None
    return duration, None, measure_per_mutant_overhead(mutant_pytest_args, cwd)
