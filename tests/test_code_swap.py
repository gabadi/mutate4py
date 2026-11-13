"""Unit tests for _code_swap.py (pure swap planner, design section 4).

Every test drives the public interface with real sources: `plan_swap` on a
clean and a mutated source, then `SwapPlan.apply` on the live functions that
the clean source produced.
"""

import dataclasses

import pytest

from mutate4py._code_swap import Refusal, SwapPlan, plan_swap

FILE = "guarded.py"


def _load(source: str) -> dict:
    """Execute the clean source the way an import would, under FILE."""
    namespace: dict = {}
    exec(compile(source, FILE, "exec"), namespace)
    return namespace


@pytest.mark.unit
def test_operator_change_in_a_function_swaps_the_live_function():
    clean = "def add(a, b):\n    return a + b\n"
    mutated = "def add(a, b):\n    return a - b\n"
    namespace = _load(clean)

    plan = plan_swap(clean, mutated, FILE, frozenset())

    assert isinstance(plan, SwapPlan)
    assert plan.apply(namespace.values()) == 1
    assert namespace["add"](5, 3) == 2


@pytest.mark.unit
def test_a_function_added_by_the_mutant_is_refused_as_shape():
    clean = "def add(a, b):\n    return a + b\n"
    mutated = "def add(a, b):\n    return a + b\n\ndef extra():\n    return 1\n"

    assert plan_swap(clean, mutated, FILE, frozenset()) == Refusal("shape")


IMPORT_TIME_CASES = {
    "decorator": (
        "def wrap(f):\n    return f\n\n@wrap\ndef add(a, b):\n    return a + b\n",
        "def wrap(f):\n    return f\n\ndef add(a, b):\n    return a + b\n",
    ),
    "default argument": (
        "def add(a, b=1):\n    return a + b\n",
        "def add(a, b=2):\n    return a + b\n",
    ),
    "module constant": (
        "SCALE = 1\n\ndef add(a, b):\n    return a + b\n",
        "SCALE = 2\n\ndef add(a, b):\n    return a + b\n",
    ),
    "class attribute": (
        "class Calc:\n    STEP = 1\n\n    def add(self, a, b):\n        return a + b\n",
        "class Calc:\n    STEP = 2\n\n    def add(self, a, b):\n        return a + b\n",
    ),
    "base class": (
        "class Calc(Base):\n    pass\n",
        "class Calc(Other):\n    pass\n",
    ),
    "annotation": (
        "def add(a: int, b):\n    return a + b\n",
        "def add(a: str, b):\n    return a + b\n",
    ),
}


@pytest.mark.unit
@pytest.mark.parametrize(("clean", "mutated"), IMPORT_TIME_CASES.values(), ids=IMPORT_TIME_CASES.keys())
def test_a_change_run_at_import_is_refused(clean, mutated):
    assert plan_swap(clean, mutated, FILE, frozenset()) == Refusal("import-time")


@pytest.mark.unit
def test_a_changed_body_that_ran_at_import_is_refused():
    clean = "def add(a, b):\n    return a + b\n\nTOTAL = add(1, 2)\n"
    mutated = "def add(a, b):\n    return a - b\n\nTOTAL = add(1, 2)\n"
    # Line 2 is the body; line 4 is the module-level call that executed it.
    ran_at_import = frozenset({1, 2, 4})

    assert plan_swap(clean, mutated, FILE, ran_at_import) == Refusal("ran at import")


@pytest.mark.unit
def test_a_def_line_that_ran_at_import_is_not_body_code():
    clean = "def add(a, b):\n    return a + b\n"
    mutated = "def add(a, b):\n    return a - b\n"
    # The module executed the def on line 1 but never called add.

    assert isinstance(plan_swap(clean, mutated, FILE, frozenset({1})), SwapPlan)


@pytest.mark.unit
def test_a_one_line_body_is_refused_when_its_def_line_ran_at_import():
    clean = "def add(a, b): return a + b\n"
    mutated = "def add(a, b): return a - b\n"

    assert plan_swap(clean, mutated, FILE, frozenset({1})) == Refusal("ran at import")


@pytest.mark.unit
def test_a_change_inside_a_nested_closure_swaps_through_the_outer_function():
    clean = "def make_adder(n):\n    def add(x):\n        return x + n\n    return add\n"
    mutated = "def make_adder(n):\n    def add(x):\n        return x - n\n    return add\n"
    namespace = _load(clean)

    plan = plan_swap(clean, mutated, FILE, frozenset())

    assert isinstance(plan, SwapPlan)
    assert plan.apply(namespace.values()) == 1
    assert namespace["make_adder"](1)(3) == 2


@pytest.mark.unit
def test_a_change_in_a_lambda_swaps_the_live_lambda():
    clean = "f = lambda a, b: a + b\n"
    mutated = "f = lambda a, b: a - b\n"
    namespace = _load(clean)

    plan = plan_swap(clean, mutated, FILE, frozenset())

    assert isinstance(plan, SwapPlan)
    assert plan.apply(namespace.values()) == 1
    assert namespace["f"](5, 3) == 2


@pytest.mark.unit
def test_a_change_in_an_async_function_swaps_the_live_coroutine_function():
    clean = "async def f(a, b):\n    return a + b\n"
    mutated = "async def f(a, b):\n    return a - b\n"
    namespace = _load(clean)

    plan = plan_swap(clean, mutated, FILE, frozenset())

    assert isinstance(plan, SwapPlan)
    assert plan.apply(namespace.values()) == 1
    coro = namespace["f"](5, 3)
    with pytest.raises(StopIteration) as finished:
        coro.send(None)
    assert finished.value.value == 2


@pytest.mark.unit
def test_a_change_in_a_generator_swaps_the_live_generator_function():
    clean = "def gen(a, b):\n    yield a + b\n"
    mutated = "def gen(a, b):\n    yield a - b\n"
    namespace = _load(clean)

    plan = plan_swap(clean, mutated, FILE, frozenset())

    assert isinstance(plan, SwapPlan)
    assert plan.apply(namespace.values()) == 1
    assert list(namespace["gen"](5, 3)) == [2]


@pytest.mark.unit
def test_a_method_that_stops_using_super_is_refused_as_freevars():
    # `a` still uses super(), so the class body keeps its __class__ cell; `m`
    # loses its free variable, which a live closure cannot take.
    clean = (
        "class C:\n    def a(self):\n        return super().a()\n\n    def m(self):\n        return super().m() + 1\n"
    )
    mutated = "class C:\n    def a(self):\n        return super().a()\n\n    def m(self):\n        return 1\n"

    assert plan_swap(clean, mutated, FILE, frozenset()) == Refusal("freevars")


@pytest.mark.unit
def test_a_plan_with_no_live_function_refuses_to_apply():
    clean = "def add(a, b):\n    return a + b\n"
    mutated = "def add(a, b):\n    return a - b\n"

    plan = plan_swap(clean, mutated, FILE, frozenset())

    assert isinstance(plan, SwapPlan)
    assert plan.apply([]) == Refusal("no live function")


@pytest.mark.unit
def test_an_unmatched_pair_leaves_the_matched_function_on_its_clean_code():
    clean = "def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n"
    mutated = "def add(a, b):\n    return a - b\n\ndef sub(a, b):\n    return a + b\n"
    namespace = _load(clean)

    plan = plan_swap(clean, mutated, FILE, frozenset())

    assert isinstance(plan, SwapPlan)
    assert plan.apply([namespace["add"]]) == Refusal("no live function")
    assert namespace["add"](5, 3) == 8


@pytest.mark.unit
def test_refusal_and_plan_are_immutable():
    refusal = Refusal("shape")
    plan = SwapPlan(())

    with pytest.raises(dataclasses.FrozenInstanceError):
        refusal.reason = "other"
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.pairs = ()


@pytest.mark.unit
def test_functions_sharing_a_qualified_name_are_told_apart():
    # Both lambdas are named `<lambda>` in the module, so the planner must keep
    # them apart by occurrence or the first one's change goes unseen.
    clean = "fs = (lambda: 1, lambda: 2)\n"
    mutated = "fs = (lambda: 3, lambda: 2)\n"
    namespace = _load(clean)

    plan = plan_swap(clean, mutated, FILE, frozenset())

    assert isinstance(plan, SwapPlan)
    assert plan.apply(namespace["fs"]) == 1
    assert [fn() for fn in namespace["fs"]] == [3, 2]
