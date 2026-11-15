"""`measure()` driven for real on the `measure_plain` fixture project.

Each test copies the fixture into tmp_path and runs one Measurement session
(about a second), so these are component tests: the orchestration runs in
this interpreter, the session in a spawned one."""

import shutil
from pathlib import Path

import pytest

from mutate4py._measurement import (
    ALL,
    MeasurementFailed,
    MeasureRequest,
    Narrowed,
    Static,
    Uncovered,
    measure,
)

FIXTURE = Path(__file__).parent / "fixtures" / "measure_plain"

# calc.py's lines, by role.
SCALE_LINE, ADD_DEF, ADD_BODY, SUB_BODY, UNUSED_BODY = 3, 6, 7, 11, 15


@pytest.fixture
def project(tmp_path) -> Path:
    root = tmp_path / "project"
    shutil.copytree(FIXTURE, root)
    (tmp_path / "scratch").mkdir()
    return root


def _measure(project: Path, *pytest_args: str):
    return measure(
        MeasureRequest(
            cwd=str(project),
            pytest_args=("-q", "-p", "no:cacheprovider", *pytest_args),
            target_files=(str(project / "calc.py"),),
            scratch_dir=str(project.parent / "scratch"),
        )
    )


@pytest.mark.component
def test_named_tests_narrow_import_time_lines_are_static_and_unreached_lines_uncovered(project):
    m = _measure(project)
    calc = str(project / "calc.py")

    assert m.outcome(calc, ADD_BODY) == Narrowed(frozenset({"tests/test_calc.py::test_add"}))
    assert m.outcome(calc, SUB_BODY) == Narrowed(
        frozenset({"tests/test_calc.py::test_sub_one", "tests/test_calc.py::test_sub_two"})
    )
    assert m.outcome(calc, SCALE_LINE) == Static()
    assert m.outcome(calc, ADD_DEF) == Static()
    assert m.outcome(calc, UNUSED_BODY) == Uncovered()
    assert m.covered_lines(calc) == {line for line in range(1, 16) if m.outcome(calc, line) != Uncovered()}
    assert (m.core, m.tests, m.positional_args) == ("ctrace", 5, ())


@pytest.mark.component
def test_positional_args_are_pytests_parsed_ones(project):
    assert _measure(project, "tests/test_calc.py").positional_args == ("tests/test_calc.py",)


@pytest.mark.component
def test_a_value_spelled_like_a_path_is_not_a_positional_arg(project):
    assert _measure(project, "-k", "tests").positional_args == ()


@pytest.mark.component
def test_only_the_target_files_are_measured(project):
    m = _measure(project)

    for unmeasured in ("tests/test_calc.py", "tests/conftest.py", "tests/helpers.py"):
        assert m.covered_lines(str(project / unmeasured)) == frozenset()


@pytest.mark.component
def test_the_users_coverage_config_is_not_read(project):
    (project / ".coveragerc").write_text("[run]\nomit = *calc.py\n")

    m = _measure(project)

    assert m.outcome(str(project / "calc.py"), ADD_BODY) == Narrowed(frozenset({"tests/test_calc.py::test_add"}))


@pytest.mark.component
def test_pytest_cov_enabled_by_the_projects_config_is_disabled(project):
    (project / "pytest.ini").write_text(
        "[pytest]\npythonpath = .\ntestpaths = tests\naddopts = --cov --cov-fail-under=100\n"
    )

    m = _measure(project)

    assert m.outcome(str(project / "calc.py"), ADD_BODY) == Narrowed(frozenset({"tests/test_calc.py::test_add"}))


@pytest.mark.component
def test_a_failing_suite_raises_with_the_failing_node_ids(project):
    (project / "tests" / "test_broken.py").write_text("def test_fails():\n    assert False\n")

    with pytest.raises(MeasurementFailed) as failed:
        _measure(project)

    assert failed.value.failing_node_ids == ("tests/test_broken.py::test_fails",)
    assert not failed.value.no_tests


@pytest.mark.component
def test_no_tests_collected_raises_the_no_tests_case(project):
    with pytest.raises(MeasurementFailed) as failed:
        _measure(project, "-k", "no_such_test")

    assert failed.value.no_tests


@pytest.mark.component
def test_a_usage_error_raises_with_pytests_error_line(project):
    with pytest.raises(MeasurementFailed) as failed:
        _measure(project, "--no-such-flag")

    assert failed.value.failing_node_ids == ()
    assert "unrecognized arguments: --no-such-flag" in failed.value.reason
    assert "exit code 4" in failed.value.reason


@pytest.mark.component
def test_a_module_fixtures_setup_counts_for_a_later_test_in_its_file(project):
    m = _measure(project)

    later = frozenset({"tests/test_slow.py::test_reuses_the_setup"})
    assert m.budget_of(later) >= 0.2
    assert m.budget_of(ALL) >= m.budget_of(later)
    assert 0.0 <= m.per_mutant_overhead < m.wall
