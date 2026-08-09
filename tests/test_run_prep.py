"""Unit tests for run-loop pre-flight setup (_run_prep.py)."""

from mutate4py._run_prep import _fork_server_eligible

# ── _fork_server_eligible ─────────────────────────────────────────────────────


def test_fork_server_eligible_true_when_all_conditions_met():
    assert (
        _fork_server_eligible(
            fork_server_requested=True, use_parallel=False, test_ctx_db=None, selected_sites=[object()]
        )
        is True
    )


def test_fork_server_eligible_false_when_not_requested():
    assert (
        _fork_server_eligible(
            fork_server_requested=False, use_parallel=False, test_ctx_db=None, selected_sites=[object()]
        )
        is False
    )


def test_fork_server_eligible_false_when_parallel():
    assert (
        _fork_server_eligible(
            fork_server_requested=True, use_parallel=True, test_ctx_db=None, selected_sites=[object()]
        )
        is False
    )


def test_fork_server_eligible_false_when_test_ctx_db_present():
    assert (
        _fork_server_eligible(
            fork_server_requested=True, use_parallel=False, test_ctx_db=object(), selected_sites=[object()]
        )
        is False
    )


def test_fork_server_eligible_false_when_no_selected_sites():
    assert (
        _fork_server_eligible(fork_server_requested=True, use_parallel=False, test_ctx_db=None, selected_sites=[])
        is False
    )
