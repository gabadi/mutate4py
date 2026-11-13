"""Unit tests for acceptance/steps/coverage_helpers.py."""

import ast
import types

import pytest

from acceptance.steps.coverage_helpers import (
    HALF_TAKEN_BRANCH_SOURCE,
    HALF_TAKEN_BRANCH_TEST,
    IMPORT_TIME_SOURCE,
    IMPORTING_CONFTEST,
    REMOVED_FLAG_MESSAGE,
    assert_exit_status,
    assert_no_backup_beside,
    assert_no_partition_counts,
    assert_output_contains,
    assert_stdout_contains,
    assert_stdout_not_contains,
    called_names,
    core_recording_test,
    first_recorded_core,
    removed_flag_refusal,
    removed_flag_tokens,
    step_param,
)


def _result(stdout="", stderr="", returncode=0):
    return types.SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


@pytest.mark.unit
def test_step_param_prefers_the_outline_value_over_the_regex_group():
    match = types.SimpleNamespace(group=lambda i: "from-regex")
    assert step_param(match, {"key": "from-outline"}, "key") == "from-outline"
    assert step_param(match, {}, "key") == "from-regex"


@pytest.mark.unit
def test_called_names_splits_on_commas_and_trims():
    assert called_names("f1, f3") == ["f1", "f3"]


@pytest.mark.unit
def test_called_names_of_an_empty_cell_is_empty():
    assert called_names("") == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "description, tokens",
    [
        ("--cov-cmd CMD", ["--cov-cmd", "true"]),
        ("--lcov cov.info", ["--lcov", "cov.info"]),
        ("--reuse-coverage", ["--reuse-coverage"]),
        ("--test-contexts DB", ["--test-contexts", "tests.coverage"]),
        ("--build-test-contexts OUT", ["--build-test-contexts", "out.coverage"]),
    ],
)
def test_removed_flag_tokens_supply_the_flag(description, tokens):
    assert removed_flag_tokens(description) == tokens


@pytest.mark.unit
def test_removed_flag_tokens_rejects_an_unknown_row():
    with pytest.raises(NotImplementedError, match="Unknown removed flag"):
        removed_flag_tokens("--cov-all")


@pytest.mark.unit
def test_removed_flag_refusal_names_the_bare_flag_and_the_replacement():
    assert removed_flag_refusal("--lcov cov.info") == "--lcov removed in 0.3.0: the run measures coverage itself"
    assert REMOVED_FLAG_MESSAGE in removed_flag_refusal("--reuse-coverage")


@pytest.mark.unit
def test_fixture_sources_parse_and_the_conftest_imports_the_module():
    for source in (IMPORT_TIME_SOURCE, HALF_TAKEN_BRANCH_SOURCE, HALF_TAKEN_BRANCH_TEST):
        ast.parse(source)
    assert IMPORTING_CONFTEST.startswith("import sample")


@pytest.mark.unit
def test_the_half_taken_branch_test_never_enters_the_if_arm():
    namespace: dict = {}
    exec(compile(HALF_TAKEN_BRANCH_SOURCE, "<sample>", "exec"), namespace)
    assert namespace["f1"](0, 1) == 0


@pytest.mark.unit
def test_core_recording_test_appends_the_core_it_ran_under(tmp_path, monkeypatch):
    record = tmp_path / "cores.txt"
    namespace: dict = {}
    exec(compile(core_recording_test(str(record)), "<test>", "exec"), namespace)
    monkeypatch.setenv("COVERAGE_CORE", "ctrace")
    namespace["test_core"]()
    monkeypatch.delenv("COVERAGE_CORE")
    namespace["test_core"]()
    assert record.read_text() == "ctrace\n(unset)\n"


@pytest.mark.unit
def test_first_recorded_core_is_the_first_line(tmp_path):
    record = tmp_path / "cores.txt"
    record.write_text("ctrace\nsysmon\n")
    assert first_recorded_core(str(record)) == "ctrace"


@pytest.mark.unit
def test_first_recorded_core_fails_when_nothing_was_recorded(tmp_path):
    with pytest.raises(AssertionError, match="no run recorded"):
        first_recorded_core(str(tmp_path / "missing.txt"))
    empty = tmp_path / "empty.txt"
    empty.write_text("")
    with pytest.raises(AssertionError, match="is empty"):
        first_recorded_core(str(empty))


@pytest.mark.unit
def test_stdout_assertions():
    assert_stdout_contains(_result(stdout="a b"), "a")
    assert_stdout_not_contains(_result(stdout="a b"), "z")
    with pytest.raises(AssertionError, match="expected 'z'"):
        assert_stdout_contains(_result(stdout="a b"), "z")
    with pytest.raises(AssertionError, match="unexpected 'a'"):
        assert_stdout_not_contains(_result(stdout="a b"), "a")


@pytest.mark.unit
def test_assert_exit_status_compares_the_return_code():
    assert_exit_status(_result(returncode=2), 2)
    with pytest.raises(AssertionError, match="expected exit 2, got 0"):
        assert_exit_status(_result(returncode=0), 2)


@pytest.mark.unit
def test_assert_output_contains_reads_both_streams():
    assert_output_contains(_result(stderr="boom"), "boom")
    assert_output_contains(_result(stdout="fine"), "fine")
    with pytest.raises(AssertionError, match="expected 'boom'"):
        assert_output_contains(_result(stdout="fine"), "boom")


@pytest.mark.unit
def test_assert_no_partition_counts():
    assert_no_partition_counts(_result(stdout="Mutation scan: x"))
    with pytest.raises(AssertionError):
        assert_no_partition_counts(_result(stdout="Covered mutation sites: 1"))
    with pytest.raises(AssertionError):
        assert_no_partition_counts(_result(stdout="Uncovered mutation sites: 1"))


@pytest.mark.unit
def test_assert_no_backup_beside(tmp_path):
    source = tmp_path / "s.py"
    assert_no_backup_beside(str(source))
    (tmp_path / "s.py.bak").write_text("")
    with pytest.raises(AssertionError, match="unexpected backup file"):
        assert_no_backup_beside(str(source))
