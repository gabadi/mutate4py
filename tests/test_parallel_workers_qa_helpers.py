"""Unit tests for acceptance/steps/parallel_workers_qa_helpers.py."""

from acceptance.steps.parallel_workers_qa_helpers import (
    BODY_ALWAYS_FAIL,
    BODY_ALWAYS_PASS,
    check_worker_tree_body,
    counted_all_killed_body,
    make_lcov,
    record_cwd_and_kill_body,
    single_survivor_body,
    sleep_past_timeout_body,
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


# ── counted_all_killed_body ─────────────────────────────────────────────


@pytest.mark.unit
def test_counted_all_killed_body_compiles():
    body = counted_all_killed_body("/tmp/counter.log")
    compile(body, "<test>", "exec")


@pytest.mark.unit
def test_counted_all_killed_body_interpolates_path():
    body = counted_all_killed_body("/tmp/counter.log")
    assert "'/tmp/counter.log'" in body


@pytest.mark.unit
def test_counted_all_killed_body_baseline_passes_mutants_fail():
    body = counted_all_killed_body("/tmp/counter.log")
    assert "count == 0" in body
    assert "assert False" in body


# ── sleep_past_timeout_body ──────────────────────────────────────────────


@pytest.mark.unit
def test_sleep_past_timeout_body_compiles():
    body = sleep_past_timeout_body("/tmp/counter.log")
    compile(body, "<test>", "exec")


@pytest.mark.unit
def test_sleep_past_timeout_body_sleeps_on_mutant_calls():
    body = sleep_past_timeout_body("/tmp/counter.log")
    assert "time.sleep(30)" in body
    assert "'/tmp/counter.log'" in body


# ── single_survivor_body ──────────────────────────────────────────────────


@pytest.mark.unit
def test_single_survivor_body_compiles():
    body = single_survivor_body("/tmp/baseline.done", "calc.py")
    compile(body, "<test>", "exec")


@pytest.mark.unit
def test_single_survivor_body_interpolates_params():
    body = single_survivor_body("/tmp/baseline.done", "calc.py")
    assert "'/tmp/baseline.done'" in body
    assert "'calc.py'" in body
    assert "a >= b" in body


# ── record_cwd_and_kill_body ────────────────────────────────────────────


@pytest.mark.unit
def test_record_cwd_and_kill_body_compiles():
    body = record_cwd_and_kill_body("/tmp/baseline.done", "/tmp/sentinels")
    compile(body, "<test>", "exec")


@pytest.mark.unit
def test_record_cwd_and_kill_body_interpolates_params():
    body = record_cwd_and_kill_body("/tmp/baseline.done", "/tmp/sentinels")
    assert "'/tmp/baseline.done'" in body
    assert "'/tmp/sentinels'" in body
    assert "assert False" in body


# ── check_worker_tree_body ──────────────────────────────────────────────


@pytest.mark.unit
def test_check_worker_tree_body_compiles():
    body = check_worker_tree_body("/tmp/baseline.done", "/tmp/first.done", "/tmp/sentinel.txt")
    compile(body, "<test>", "exec")


@pytest.mark.unit
def test_check_worker_tree_body_interpolates_params():
    body = check_worker_tree_body("/tmp/baseline.done", "/tmp/first.done", "/tmp/sentinel.txt")
    assert "'/tmp/baseline.done'" in body
    assert "'/tmp/first.done'" in body
    assert "'/tmp/sentinel.txt'" in body
    assert "workers" in body
