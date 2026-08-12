"""Guardrail: every test whose work spawns a fresh Python interpreter must
carry @pytest.mark.integration or @pytest.mark.component.

A spawned interpreter's *own* work is invisible to pytest-cov's
--cov-context=test (see ADR 0018) — that coverage-blindness is why
`integration` exists, and it's excluded from the mutation run's default test
command (see justfile's `mutate` recipe) so its ~5-6s-per-invocation cost
doesn't reintroduce the ~28-minute full `src/` sweep issue #18 fixed.
`component` tests (ADR 0023) may also spawn an interpreter as an incidental
implementation detail (e.g. a fake runner injected into otherwise in-process
orchestration code, see tests/test_test_context_build.py) while the test's
*own* meaningful work stays in-process and cov-context-visible; they are
excluded from the fast `test-unit` loop but stay eligible for narrowing, so
either marker satisfies this guard's real concern — keeping spawn cost out of
the fast dev-loop gate — while only `unit` (unmarked here) is disqualifying.
"""

import ast
import os
import pytest


TESTS_DIR = os.path.dirname(__file__)

SPAWN_FUNCS = {"run", "Popen", "call", "check_output", "check_call"}
KNOWN_INTERPRETER_HELPERS = {"_run_cli_path", "_run_cli_in"}


_NON_DISQUALIFYING_MARKERS = {"integration", "component"}


def _has_integration_marker(node: ast.FunctionDef) -> bool:
    for dec in node.decorator_list:
        if (
            isinstance(dec, ast.Attribute)
            and dec.attr in _NON_DISQUALIFYING_MARKERS
            and isinstance(dec.value, ast.Attribute)
            and dec.value.attr == "mark"
        ):
            return True
    return False


def _spawns_interpreter(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Name) and func.id in KNOWN_INTERPRETER_HELPERS:
        return True
    is_subprocess_spawn = isinstance(func, ast.Attribute) and func.attr in SPAWN_FUNCS
    if not is_subprocess_spawn:
        return False
    return any(isinstance(arg, ast.Attribute) and arg.attr == "executable" for arg in ast.walk(call))


def _find_unmarked_interpreter_spawning_tests(path: str) -> list[str]:
    with open(path) as f:
        source = f.read()
    tree = ast.parse(source, filename=path)
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        if _has_integration_marker(node):
            continue
        spawns = any(isinstance(n, ast.Call) and _spawns_interpreter(n) for n in ast.walk(node))
        if spawns:
            violations.append(node.name)
    return violations


@pytest.mark.unit
def test_no_unmarked_interpreter_spawning_tests():
    violations = {}
    for fname in sorted(os.listdir(TESTS_DIR)):
        if not fname.startswith("test_") or not fname.endswith(".py"):
            continue
        path = os.path.join(TESTS_DIR, fname)
        found = _find_unmarked_interpreter_spawning_tests(path)
        if found:
            violations[fname] = found

    assert not violations, (
        "Test(s) spawn a fresh Python interpreter (subprocess.run/Popen/... "
        "with sys.executable, or _run_cli_path/_run_cli_in) without "
        "@pytest.mark.integration or @pytest.mark.component, which will "
        "silently re-enter the fast test-unit loop:\n" + "\n".join(f"  {f}: {names}" for f, names in violations.items())
    )
