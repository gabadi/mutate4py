"""Shared step-handler registry utilities for acceptance step modules."""
import os
import re
import subprocess

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class QAState:
    """Mutable state bag for QA step modules (report output + fixture paths)."""
    def __init__(self, source_path: str, lcov_path: str):
        self.report_output: str = ""
        self.source_path: str = source_path
        self.lcov_path: str = lcov_path


def check_cli_available() -> bool:
    """Return True if crap4py.__main__ is importable (CLI entrypoint exists)."""
    result = subprocess.run(
        ["uv", "run", "python", "-c", "import crap4py.__main__"],
        cwd=_REPO_ROOT,
        capture_output=True,
    )
    return result.returncode == 0


def run_cli(lcov_path: str, source_path: str, cli_available: bool) -> str:
    """Run 'uv run crap4py --lcov <lcov> <source>' and return stdout, or '' if CLI absent."""
    if not cli_available:
        return ""
    result = subprocess.run(
        ["uv", "run", "crap4py", "--lcov", lcov_path, source_path],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.stdout


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
