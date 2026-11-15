"""Shared step-handler registry utilities for acceptance step modules."""

import os
import re
import subprocess

from acceptance.steps.nested_pytest_helpers import nested_pytest_env

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def run_mutate4py(*args: str) -> subprocess.CompletedProcess:
    """Run 'uv run mutate4py <args>' and return the CompletedProcess."""
    return subprocess.run(
        ["uv", "run", "mutate4py"] + list(args),
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        env=nested_pytest_env(),
    )


def assert_nonzero_exit(
    result: subprocess.CompletedProcess, label: str = "exit"
) -> None:
    assert result.returncode != 0, f"expected non-zero {label}, got {result.returncode}"


def assert_no_scan_block(result: subprocess.CompletedProcess) -> None:
    assert "Mutation scan:" not in result.stdout, (
        f"scan block unexpectedly in stdout:\n{result.stdout}"
    )


def make_registry():
    """Return a (STEP_HANDLERS dict, step decorator, run_step fn) triple."""
    handlers = {}

    def step(pattern):
        def decorator(fn):
            handlers[pattern] = fn
            return fn

        return decorator

    def run_step(keyword: str, text: str, params: dict) -> None:
        for pattern, handler in handlers.items():
            m = re.fullmatch(pattern, text)
            if m:
                handler(m, params)
                return
        raise NotImplementedError(f"No step handler for: {keyword} {text!r}")

    return handlers, step, run_step
