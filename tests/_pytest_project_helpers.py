"""Shared helpers for tests that need a real pytest project under a target
run's cwd — used wherever a test only cares about run_mutations' dispatch,
report, or classification mechanics, and used to rely on a disconnected
shell stand-in (e.g. "exit 0", a hand-rolled grep-based script) that no
longer exists now that pytest is the only supported runner, invoked
directly rather than through a shell.
"""

import os

__all__ = [
    "write_always_failing_pytest_project",
    "write_always_passing_pytest_project",
    "write_content_check_pytest_project",
    "write_sleep_if_mutated_pytest_project",
]

_TESTS_DIRNAME = "tests"


def _tests_dir(cwd: str) -> str:
    tests_dir = os.path.join(cwd, _TESTS_DIRNAME)
    os.makedirs(tests_dir, exist_ok=True)
    return tests_dir


def write_always_passing_pytest_project(cwd: str) -> list[str]:
    """Write a trivial always-passing test into cwd/tests; return the
    pytest_args that select just it."""
    with open(os.path.join(_tests_dir(cwd), "test_always_passes.py"), "w") as f:
        f.write("def test_ok():\n    assert True\n")
    return ["-q", "tests"]


def write_always_failing_pytest_project(cwd: str) -> list[str]:
    """Write a trivial always-failing test into cwd/tests; return the
    pytest_args that select just it."""
    with open(os.path.join(_tests_dir(cwd), "test_always_fails.py"), "w") as f:
        f.write("def test_fail():\n    assert False\n")
    return ["-q", "tests"]


def write_content_check_pytest_project(cwd: str, target_path: str, forbidden_text: str) -> list[str]:
    """Write a real pytest test that fails iff target_path currently
    contains forbidden_text — the pytest-native replacement for a
    grep-based shell stand-in that inspected the mutated source on disk."""
    test_body = (
        "def test_not_mutated():\n"
        f"    with open({target_path!r}) as f:\n"
        "        content = f.read()\n"
        f"    assert {forbidden_text!r} not in content\n"
    )
    with open(os.path.join(_tests_dir(cwd), "test_content_check.py"), "w") as f:
        f.write(test_body)
    return ["-q", "tests"]


def write_sleep_if_mutated_pytest_project(
    cwd: str, target_path: str, mutant_text: str, sleep_seconds: float
) -> list[str]:
    """Write a real pytest test that passes quickly unless target_path
    currently contains mutant_text, in which case it sleeps past a short
    timeout — the pytest-native replacement for a grep-then-sleep shell
    stand-in."""
    test_body = (
        "import time\n\n"
        "def test_maybe_slow():\n"
        f"    with open({target_path!r}) as f:\n"
        "        content = f.read()\n"
        f"    if {mutant_text!r} in content:\n"
        f"        time.sleep({sleep_seconds})\n"
    )
    with open(os.path.join(_tests_dir(cwd), "test_timeout_check.py"), "w") as f:
        f.write(test_body)
    return ["-q", "tests"]
