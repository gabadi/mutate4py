"""Unit tests for acceptance/steps/run_loop_qa_helpers.py."""

from acceptance.steps.run_loop_qa_helpers import (
    BODY_ALWAYS_FAIL,
    BODY_ALWAYS_PASS,
    all_killed_body,
    make_lcov,
    mutated_run_exits_nonzero_body,
    mutated_run_sleeps_past_timeout_body,
    n_survivors_body,
    one_timeout_rest_killed_body,
)
import pytest


# ── constants ─────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_body_always_pass_compiles_and_passes():
    ns = {}
    exec(compile(BODY_ALWAYS_PASS, "<test>", "exec"), ns)
    ns["test_qa"]()


@pytest.mark.unit
def test_body_always_fail_compiles_and_raises():
    ns = {}
    exec(compile(BODY_ALWAYS_FAIL, "<test>", "exec"), ns)
    try:
        ns["test_qa"]()
        assert False, "expected AssertionError"
    except AssertionError:
        pass


# ── make_lcov ────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_make_lcov_format():
    text = make_lcov("/src/foo.py", [3, 1])
    assert "SF:/src/foo.py" in text
    assert "DA:1,1" in text
    assert "DA:3,1" in text
    assert "end_of_record" in text


@pytest.mark.unit
def test_make_lcov_sorts_lines():
    text = make_lcov("/src/foo.py", [5, 2])
    da_lines = [ln for ln in text.splitlines() if ln.startswith("DA:")]
    assert da_lines == ["DA:2,1", "DA:5,1"]


# ── mutated_run_exits_nonzero_body ───────────────────────────────────────


@pytest.mark.unit
def test_mutated_run_exits_nonzero_body_compiles():
    body = mutated_run_exits_nonzero_body("/tmp/calc.py")
    compile(body, "<test>", "exec")


@pytest.mark.unit
def test_mutated_run_exits_nonzero_body_interpolates_path():
    body = mutated_run_exits_nonzero_body("/tmp/calc.py")
    assert "'/tmp/calc.py'" in body
    assert ">=|<=" in body


# ── mutated_run_sleeps_past_timeout_body ─────────────────────────────────


@pytest.mark.unit
def test_mutated_run_sleeps_past_timeout_body_compiles():
    body = mutated_run_sleeps_past_timeout_body("/tmp/calc.py")
    compile(body, "<test>", "exec")


@pytest.mark.unit
def test_mutated_run_sleeps_past_timeout_body_interpolates_path():
    body = mutated_run_sleeps_past_timeout_body("/tmp/calc.py")
    assert "'/tmp/calc.py'" in body
    assert "time.sleep(30)" in body


# ── one_timeout_rest_killed_body ─────────────────────────────────────────


@pytest.mark.unit
def test_one_timeout_rest_killed_body_compiles():
    body = one_timeout_rest_killed_body("/tmp/counter.log")
    compile(body, "<test>", "exec")


@pytest.mark.unit
def test_one_timeout_rest_killed_body_interpolates_path():
    body = one_timeout_rest_killed_body("/tmp/counter.log")
    assert "'/tmp/counter.log'" in body
    assert "time.sleep(30)" in body
    assert "assert False" in body


# ── n_survivors_body ──────────────────────────────────────────────────────


def _verdicts(tmp_path, n: int, source: str) -> bool:
    """True when the fake test passes against `source` (the Mutant survives)."""
    calc = tmp_path / "calc.py"
    calc.write_text(source)
    namespace: dict = {}
    exec(n_survivors_body(str(calc), n), namespace)
    try:
        namespace["test_qa"]()
    except AssertionError:
        return False
    return True


@pytest.mark.unit
def test_n_survivors_body_compiles():
    body = n_survivors_body("/tmp/calc.py", 1)
    compile(body, "<test>", "exec")


@pytest.mark.unit
def test_n_survivors_body_passes_on_the_unmutated_source(tmp_path):
    assert _verdicts(tmp_path, 0, "return a > b\nreturn c > d\n")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("n", "first_survives", "second_survives"),
    [(0, False, False), (1, True, False), (2, True, True)],
)
def test_n_survivors_body_lets_the_first_n_sites_mutants_pass(tmp_path, n, first_survives, second_survives):
    assert _verdicts(tmp_path, n, "return a >= b\nreturn c > d\n") is first_survives
    assert _verdicts(tmp_path, n, "return a > b\nreturn c >= d\n") is second_survives


@pytest.mark.unit
def test_n_survivors_body_gives_the_same_verdict_every_time_it_is_run(tmp_path):
    source = "return a >= b\nreturn c > d\n"
    assert [_verdicts(tmp_path, 1, source) for _ in range(3)] == [True, True, True]


# ── all_killed_body ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_all_killed_body_compiles():
    body = all_killed_body("/tmp/counter.log")
    compile(body, "<test>", "exec")


@pytest.mark.unit
def test_all_killed_body_interpolates_path():
    body = all_killed_body("/tmp/counter.log")
    assert "'/tmp/counter.log'" in body
    assert "assert False" in body
