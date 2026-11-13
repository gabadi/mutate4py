"""Pure builders for the pytest projects the acceptance steps write to disk.

A run measures coverage itself (ADR 0027), so a scenario's fixture is a real
pytest project: a source module plus tests that import it and reach its mutation
sites. These functions build the source and test texts from parameters, with no
filesystem or subprocess coupling, so they have unit tests in
tests/test_run_loop_helpers.py.
"""

SAMPLE_MODULE = "sample"

# An empty conftest.py in the project root puts that directory on sys.path, so
# tests under tests/ import the module next to it.
ROOT_CONFTEST = ""

_KILL = "kill"
_SURVIVE = "survive"
_TIMEOUT = "timeout"
_OUTCOMES = (_KILL, _SURVIVE, _TIMEOUT)

FAILING_TEST_BODY = "def test_qa():\n    assert False\n"


def function_names(count: int) -> list[str]:
    """The function names f1..f<count> that compare_source defines."""
    return [f"f{i}" for i in range(1, count + 1)]


def compare_source(count: int) -> tuple[str, list[int]]:
    """A module of `count` functions, each returning `a > b`.

    Returns (source, the line of each function's comparison site)."""
    lines: list[str] = []
    site_lines: list[int] = []
    for name in function_names(count):
        lines.append(f"def {name}(a, b):")
        lines.append("    return a > b")
        site_lines.append(len(lines))
        lines.append("")
    return "\n".join(lines) + "\n", site_lines


def outcome_test_body(module: str, outcomes: dict[str, str]) -> str:
    """Tests, one per function, whose result under that function's `>=` Mutant is `outcome`.

    "kill" fails on the Mutant (the original is false for equal operands, the
    Mutant true), "timeout" sleeps past any timeout on the Mutant, and "survive"
    calls the function without checking the result. All pass on the original code."""
    unknown = sorted(set(outcomes.values()) - set(_OUTCOMES))
    if unknown:
        raise ValueError(f"Unknown outcome: {unknown[0]!r}; expected one of {_OUTCOMES}")
    parts = ["import time", "", f"import {module}", "", ""]
    for name, outcome in outcomes.items():
        parts.append(f"def test_{name}():")
        if outcome == _KILL:
            parts.append(f"    assert not {module}.{name}(1, 1)")
        elif outcome == _TIMEOUT:
            parts.append(f"    if {module}.{name}(1, 1):")
            parts.append("        time.sleep(60)")
        else:
            parts.append(f"    {module}.{name}(2, 1)")
        parts.extend(["", ""])
    return "\n".join(parts).rstrip("\n") + "\n"


def reaching_test_body(module: str, names: list[str]) -> str:
    """Tests that call every name once and check nothing: all sites covered, every Mutant survives."""
    return outcome_test_body(module, {name: _SURVIVE for name in names})


def uncalled_source(count: int, first_index: int) -> str:
    """`count` further comparison functions u<first_index>.. that no test calls."""
    lines: list[str] = []
    for i in range(first_index, first_index + count):
        lines.append(f"def u{i}(a, b):")
        lines.append("    return a > b")
        lines.append("")
    return "\n".join(lines) + "\n"
