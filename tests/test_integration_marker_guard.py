"""Guardrail: every test whose work runs inside a spawned Python interpreter
must carry @pytest.mark.integration.

A spawned interpreter is invisible to pytest-cov's --cov-context=test, so
nothing that happens inside it can contribute per-Mutant test narrowing (see
ADR 0018). That coverage-blindness, not the interpreter spawn itself, is why
the marker exists — spawning is only how this guard detects it. Unmarked
interpreter-spawning tests silently end up in the mutation run's test command
(which defaults to excluding `integration`-marked tests, see justfile's
`mutate` recipe) and reintroduce the ~5-6s-per-invocation cost that made the
full `src/` mutation sweep take ~28 minutes — a symptom of the
coverage-blindness, not the criterion for the marker.
"""

import ast
import os

TESTS_DIR = os.path.dirname(__file__)

SPAWN_FUNCS = {"run", "Popen", "call", "check_output", "check_call"}
KNOWN_INTERPRETER_HELPERS = {"_run_cli_path", "_run_cli_in"}


def _has_integration_marker(node: ast.FunctionDef) -> bool:
    for dec in node.decorator_list:
        if (
            isinstance(dec, ast.Attribute)
            and dec.attr == "integration"
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
        "@pytest.mark.integration, which will silently re-enter the "
        "mutation run's test command:\n" + "\n".join(f"  {f}: {names}" for f, names in violations.items())
    )
