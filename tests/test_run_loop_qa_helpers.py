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


# ── constants ─────────────────────────────────────────────────────────────


def test_body_always_pass_compiles_and_passes():
    ns = {}
    exec(compile(BODY_ALWAYS_PASS, "<test>", "exec"), ns)
    ns["test_qa"]()


def test_body_always_fail_compiles_and_raises():
    ns = {}
    exec(compile(BODY_ALWAYS_FAIL, "<test>", "exec"), ns)
    try:
        ns["test_qa"]()
        assert False, "expected AssertionError"
    except AssertionError:
        pass


# ── make_lcov ────────────────────────────────────────────────────────────


def test_make_lcov_format():
    text = make_lcov("/src/foo.py", [3, 1])
    assert "SF:/src/foo.py" in text
    assert "DA:1,1" in text
    assert "DA:3,1" in text
    assert "end_of_record" in text


def test_make_lcov_sorts_lines():
    text = make_lcov("/src/foo.py", [5, 2])
    da_lines = [ln for ln in text.splitlines() if ln.startswith("DA:")]
    assert da_lines == ["DA:2,1", "DA:5,1"]


# ── mutated_run_exits_nonzero_body ───────────────────────────────────────


def test_mutated_run_exits_nonzero_body_compiles():
    body = mutated_run_exits_nonzero_body("/tmp/calc.py")
    compile(body, "<test>", "exec")


def test_mutated_run_exits_nonzero_body_interpolates_path():
    body = mutated_run_exits_nonzero_body("/tmp/calc.py")
    assert "'/tmp/calc.py'" in body
    assert ">=|<=" in body


# ── mutated_run_sleeps_past_timeout_body ─────────────────────────────────


def test_mutated_run_sleeps_past_timeout_body_compiles():
    body = mutated_run_sleeps_past_timeout_body("/tmp/calc.py")
    compile(body, "<test>", "exec")


def test_mutated_run_sleeps_past_timeout_body_interpolates_path():
    body = mutated_run_sleeps_past_timeout_body("/tmp/calc.py")
    assert "'/tmp/calc.py'" in body
    assert "time.sleep(30)" in body


# ── one_timeout_rest_killed_body ─────────────────────────────────────────


def test_one_timeout_rest_killed_body_compiles():
    body = one_timeout_rest_killed_body("/tmp/counter.log")
    compile(body, "<test>", "exec")


def test_one_timeout_rest_killed_body_interpolates_path():
    body = one_timeout_rest_killed_body("/tmp/counter.log")
    assert "'/tmp/counter.log'" in body
    assert "time.sleep(30)" in body
    assert "assert False" in body


# ── n_survivors_body ──────────────────────────────────────────────────────


def test_n_survivors_body_compiles():
    body = n_survivors_body("/tmp/counter.log", 3)
    compile(body, "<test>", "exec")


def test_n_survivors_body_interpolates_params():
    body = n_survivors_body("/tmp/counter.log", 3)
    assert "'/tmp/counter.log'" in body
    assert "count <= 3" in body


# ── all_killed_body ───────────────────────────────────────────────────────


def test_all_killed_body_compiles():
    body = all_killed_body("/tmp/counter.log")
    compile(body, "<test>", "exec")


def test_all_killed_body_interpolates_path():
    body = all_killed_body("/tmp/counter.log")
    assert "'/tmp/counter.log'" in body
    assert "assert False" in body
