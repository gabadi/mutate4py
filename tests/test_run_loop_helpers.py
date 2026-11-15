"""Unit tests for acceptance/steps/run_loop_helpers.py."""

import ast
import sys
import types

import pytest

from acceptance.steps.run_loop_helpers import (
    FAILING_TEST_BODY,
    SAMPLE_MODULE,
    compare_source,
    function_names,
    outcome_test_body,
    reaching_test_body,
    uncalled_source,
)


def _load(source: str, name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    exec(compile(source, f"<{name}>", "exec"), module.__dict__)
    return module


@pytest.fixture
def sample(monkeypatch):
    """A `sample` module of three comparison functions, importable by name."""
    source, _ = compare_source(3)
    module = _load(source, SAMPLE_MODULE)
    monkeypatch.setitem(sys.modules, SAMPLE_MODULE, module)
    return module


def _mutated(monkeypatch, source: str) -> None:
    monkeypatch.setitem(sys.modules, SAMPLE_MODULE, _load(source.replace("a > b", "a >= b"), SAMPLE_MODULE))


def _run_tests(body: str) -> dict[str, BaseException | None]:
    """Run every test function in `body`; map its name to the exception it raised, or None."""
    namespace: dict = {}
    exec(compile(body, "<tests>", "exec"), namespace)
    results: dict[str, BaseException | None] = {}
    for name, fn in namespace.items():
        if name.startswith("test_"):
            try:
                fn()
            except BaseException as error:  # noqa: BLE001 - the verdict is the point
                results[name] = error
            else:
                results[name] = None
    return results


@pytest.mark.unit
def test_function_names_counts_from_one():
    assert function_names(3) == ["f1", "f2", "f3"]
    assert function_names(0) == []


@pytest.mark.unit
def test_compare_source_defines_one_comparison_per_function():
    source, site_lines = compare_source(2)
    assert source == "def f1(a, b):\n    return a > b\n\ndef f2(a, b):\n    return a > b\n\n"
    assert site_lines == [2, 5]
    assert [source.splitlines()[line - 1] for line in site_lines] == ["    return a > b"] * 2


@pytest.mark.unit
def test_compare_source_of_nothing_is_a_blank_file():
    source, site_lines = compare_source(0)
    assert site_lines == []
    assert ast.parse(source).body == []


@pytest.mark.unit
def test_every_outcome_test_passes_on_the_original_code(sample):
    body = outcome_test_body("sample", {"f1": "kill", "f2": "survive", "f3": "timeout"})
    assert _run_tests(body) == {"test_f1": None, "test_f2": None, "test_f3": None}


@pytest.mark.unit
def test_a_kill_test_fails_on_its_functions_mutant_only(monkeypatch):
    source, _ = compare_source(2)
    _mutated(monkeypatch, source)
    results = _run_tests(outcome_test_body("sample", {"f1": "kill", "f2": "survive"}))
    assert isinstance(results["test_f1"], AssertionError)
    assert results["test_f2"] is None


@pytest.mark.unit
def test_a_timeout_test_sleeps_on_the_mutant_and_not_on_the_original(monkeypatch, sample):
    naps: list[float] = []
    monkeypatch.setattr("time.sleep", naps.append)
    body = outcome_test_body("sample", {"f1": "timeout"})
    _run_tests(body)
    assert naps == []
    source, _ = compare_source(1)
    _mutated(monkeypatch, source)
    _run_tests(body)
    assert naps == [60]


@pytest.mark.unit
def test_outcome_test_body_rejects_an_unknown_outcome():
    with pytest.raises(ValueError, match="Unknown outcome: 'explode'"):
        outcome_test_body("sample", {"f1": "explode"})


@pytest.mark.unit
def test_reaching_test_body_calls_every_name_and_checks_nothing(monkeypatch):
    source, _ = compare_source(2)
    _mutated(monkeypatch, source)
    assert _run_tests(reaching_test_body("sample", ["f1", "f2"])) == {"test_f1": None, "test_f2": None}


@pytest.mark.unit
def test_reaching_test_body_reaches_each_site(sample):
    calls: list[str] = []
    for name in ("f1", "f2", "f3"):
        original = getattr(sample, name)
        setattr(sample, name, lambda a, b, _n=name, _o=original: calls.append(_n) or _o(a, b))
    _run_tests(reaching_test_body("sample", ["f1", "f3"]))
    assert calls == ["f1", "f3"]


@pytest.mark.unit
def test_failing_test_body_fails():
    assert isinstance(_run_tests(FAILING_TEST_BODY)["test_qa"], AssertionError)


@pytest.mark.unit
def test_uncalled_source_numbers_its_functions_from_the_first_index():
    source = uncalled_source(2, 4)
    assert [node.name for node in ast.parse(source).body] == ["u4", "u5"]
    assert uncalled_source(0, 1).strip() == ""


@pytest.mark.unit
def test_a_probe_opens_every_test_before_its_check():
    body = outcome_test_body("sample", {"f1": "kill", "f2": "survive"}, probe="seen.append(1)")
    tree = ast.parse(body)
    tests = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    assert [ast.unparse(t.body[0]) for t in tests] == ["seen.append(1)", "seen.append(1)"]
    assert len(tests[0].body) == 2


@pytest.mark.unit
def test_no_probe_leaves_the_tests_unchanged():
    assert outcome_test_body("sample", {"f1": "kill"}) == outcome_test_body("sample", {"f1": "kill"}, probe="")
    assert "seen" not in outcome_test_body("sample", {"f1": "kill"})
