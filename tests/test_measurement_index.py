"""The Measurement built from one session's coverage data and record.

Drives the pure builder behind `measure()` with an in-memory CoverageData, so
each case states its contexts directly instead of arranging a pytest run."""

import pytest
from coverage import CoverageData

from mutate4py._measure_record import FixtureSetup, MeasureRecord, Timing
from mutate4py._measurement import (
    ALL,
    CoverageCoreRefused,
    MeasurementFailed,
    MeasureRequest,
    Narrowed,
    Static,
    Uncovered,
    measurement_from,
    raise_for_session,
)

TARGET = "/proj/pkg/mod.py"


_OPEN_DATA: list[CoverageData] = []


@pytest.fixture(autouse=True)
def _close_data():
    yield
    while _OPEN_DATA:
        _OPEN_DATA.pop().close(force=True)


def _data(lines_by_context: dict[str, list[int]], path: str = TARGET) -> CoverageData:
    data = CoverageData(no_disk=True)
    _OPEN_DATA.append(data)
    for context, lines in lines_by_context.items():
        data.set_context(context)
        data.add_lines({path: lines})
    return data


def _record(**overrides) -> MeasureRecord:
    fields = {
        "core": "ctrace",
        "collected": 2,
        "args": ("tests",),
        "rootdir": "/proj",
        "inipath": None,
        "tests": {},
        "requested": {},
        "fixture_setups": (),
        "failed": (),
        "test_files": (),
        "conftests": (),
        "support_modules": (),
    }
    fields.update(overrides)
    return MeasureRecord(**fields)


@pytest.mark.unit
def test_a_line_reached_by_named_tests_is_narrowed_to_exactly_those_tests():
    data = _data({"": [1], "tests/test_a.py::test_x": [3, 4], "tests/test_b.py::test_y": [4]})

    m = measurement_from(data, _record(), wall=1.0)

    assert m.outcome(TARGET, 3) == Narrowed(frozenset({"tests/test_a.py::test_x"}))
    assert m.outcome(TARGET, 4) == Narrowed(frozenset({"tests/test_a.py::test_x", "tests/test_b.py::test_y"}))


@pytest.mark.unit
def test_a_line_reached_only_outside_any_test_is_static():
    m = measurement_from(_data({"": [1, 2]}), _record(), wall=1.0)

    assert m.outcome(TARGET, 1) == Static()


@pytest.mark.unit
def test_a_line_reached_at_import_and_by_a_test_is_narrowed():
    m = measurement_from(_data({"": [2], "tests/test_a.py::test_x": [2]}), _record(), wall=1.0)

    assert m.outcome(TARGET, 2) == Narrowed(frozenset({"tests/test_a.py::test_x"}))


@pytest.mark.unit
def test_an_unreached_line_or_unmeasured_file_is_uncovered():
    m = measurement_from(_data({"tests/test_a.py::test_x": [3]}), _record(), wall=1.0)

    assert m.outcome(TARGET, 9) == Uncovered()
    assert m.outcome("/proj/pkg/other.py", 3) == Uncovered()


@pytest.mark.unit
def test_tests_for_line_names_the_reaching_tests_sorted_when_narrowed():
    data = _data({"": [1], "tests/test_b.py::test_y": [4], "tests/test_a.py::test_x": [4]})

    m = measurement_from(data, _record(), wall=1.0)

    assert m.tests_for_line(TARGET, 4) == ("narrowed", ["tests/test_a.py::test_x", "tests/test_b.py::test_y"])


@pytest.mark.unit
def test_rootdir_is_the_pytest_rootdir_the_node_ids_are_relative_to():
    assert measurement_from(_data({}), _record(rootdir="/proj/member"), wall=1.0).rootdir == "/proj/member"


@pytest.mark.unit
def test_tests_for_line_is_static_with_no_tests_when_only_import_time_reached_it():
    m = measurement_from(_data({"": [1]}), _record(), wall=1.0)

    assert m.tests_for_line(TARGET, 1) == ("static", [])


@pytest.mark.unit
def test_tests_for_line_is_uncovered_with_no_tests_when_nothing_reached_it():
    m = measurement_from(_data({"tests/test_a.py::test_x": [3]}), _record(), wall=1.0)

    assert m.tests_for_line(TARGET, 9) == ("uncovered", [])
    assert m.tests_for_line("/proj/pkg/other.py", 3) == ("uncovered", [])


@pytest.mark.unit
def test_covered_lines_are_every_line_any_context_reached_and_empty_lines_the_import_time_ones():
    m = measurement_from(_data({"": [1, 2], "tests/test_a.py::test_x": [2, 5]}), _record(), wall=1.0)

    assert m.covered_lines(TARGET) == frozenset({1, 2, 5})
    assert m.empty_lines(TARGET) == frozenset({1, 2})
    assert m.covered_lines("/proj/pkg/other.py") == frozenset()


def _timed_record() -> MeasureRecord:
    return _record(
        tests={
            "tests/test_a.py::t1": Timing(duration=1.0, setup=0.0),
            "tests/test_a.py::t2": Timing(duration=0.5, setup=0.0),
            "tests/test_b.py::t3": Timing(duration=0.25, setup=0.0),
        },
        requested={"tests/test_a.py::t1": ("mod_fix", "sess"), "tests/test_b.py::t3": ("sess", "fn")},
        fixture_setups=(
            FixtureSetup("mod_fix", "module", 2.0, "tests/test_a.py"),
            FixtureSetup("sess", "session", 3.0, "tests/test_a.py"),
            FixtureSetup("fn", "function", 0.125, "tests/test_b.py"),
        ),
    )


@pytest.mark.unit
def test_the_budget_adds_the_largest_fixture_setup_seen_in_the_tests_files():
    m = measurement_from(_data({}), _timed_record(), wall=5.0)

    assert m.budget_of(frozenset({"tests/test_a.py::t2"})) == 3.5


@pytest.mark.unit
def test_a_session_fixture_counts_for_every_file_whose_tests_request_it():
    m = measurement_from(_data({}), _timed_record(), wall=5.0)

    assert m.budget_of(frozenset({"tests/test_b.py::t3"})) == 3.25


@pytest.mark.unit
def test_the_full_set_budget_sums_every_test_plus_the_largest_setup():
    m = measurement_from(_data({}), _timed_record(), wall=5.0)

    assert m.budget_of(ALL) == 4.75


@pytest.mark.unit
def test_a_test_with_no_recorded_duration_counts_as_the_longest_measured_test():
    m = measurement_from(_data({}), _timed_record(), wall=5.0)

    assert m.budget_of(frozenset({"tests/test_c.py::t9"})) == 1.0


@pytest.mark.unit
def test_per_mutant_overhead_is_the_wall_time_not_spent_in_tests():
    assert measurement_from(_data({}), _timed_record(), wall=5.0).per_mutant_overhead == 3.25
    assert measurement_from(_data({}), _timed_record(), wall=1.0).per_mutant_overhead == 0.0


@pytest.mark.unit
def test_the_session_facts_are_carried_on_the_measurement():
    m = measurement_from(_data({}), _record(collected=7, args=("tests/unit", "tests/x.py")), wall=2.0)

    assert (m.tests, m.positional_args, m.core, m.wall, m.note) == (
        7,
        ("tests/unit", "tests/x.py"),
        "ctrace",
        2.0,
        None,
    )


@pytest.mark.unit
def test_a_sysmon_core_is_refused_with_a_hint():
    with pytest.raises(CoverageCoreRefused) as refused:
        measurement_from(_data({}), _record(core="sysmon"), wall=1.0)

    assert refused.value.core == "sysmon"
    assert "COVERAGE_CORE" in refused.value.hint


@pytest.mark.unit
def test_a_pytrace_core_proceeds_with_a_note():
    m = measurement_from(_data({}), _record(core="pytrace"), wall=1.0)

    assert m.core == "pytrace"
    assert "pytrace" in m.note


# --- The session's exit status: the Measurement is the Baseline --------------


@pytest.mark.unit
def test_a_passing_session_with_a_record_raises_nothing():
    raise_for_session(0, b"5 passed\n", _record())


@pytest.mark.unit
def test_exit_5_is_the_no_tests_case():
    with pytest.raises(MeasurementFailed) as failed:
        raise_for_session(5, b"no tests ran\n", _record())

    assert failed.value.no_tests


@pytest.mark.unit
def test_a_failing_session_names_the_failing_node_ids():
    with pytest.raises(MeasurementFailed) as failed:
        raise_for_session(1, b"1 failed\n", _record(failed=("tests/test_a.py::test_x",)))

    assert failed.value.failing_node_ids == ("tests/test_a.py::test_x",)
    assert not failed.value.no_tests
    assert "tests/test_a.py::test_x" in str(failed.value)


@pytest.mark.unit
def test_a_session_that_wrote_no_record_reports_pytests_last_error_line():
    output = (
        b"ERROR: usage: pytest [options]\npytest: error: unrecognized arguments: --nope\n  rootdir: /p/test_error\n"
    )

    with pytest.raises(MeasurementFailed) as failed:
        raise_for_session(4, output, None)

    assert failed.value.failing_node_ids == ()
    assert failed.value.reason == "pytest: error: unrecognized arguments: --nope (exit code 4)"


@pytest.mark.unit
def test_a_passing_exit_without_a_record_still_fails():
    with pytest.raises(MeasurementFailed) as failed:
        raise_for_session(0, b"", None)

    assert failed.value.reason == "exit code 0"


@pytest.mark.unit
def test_a_failed_session_reason_reads_the_error_line_pytest_printed_to_stdout():
    output = b"ImportError while loading conftest\nModuleNotFoundError: No module named 'demo'\n"

    with pytest.raises(MeasurementFailed) as failed:
        raise_for_session(2, output, None)

    assert failed.value.reason == "ModuleNotFoundError: No module named 'demo' (exit code 2)"


@pytest.mark.unit
def test_a_failed_session_reason_prefers_the_last_error_line():
    with pytest.raises(MeasurementFailed) as failed:
        raise_for_session(2, b"Error: first\nunrelated line\nError: last one\n", None)

    assert failed.value.reason == "Error: last one (exit code 2)"


@pytest.mark.unit
def test_a_failed_session_without_an_error_line_reports_its_last_line():
    with pytest.raises(MeasurementFailed) as failed:
        raise_for_session(3, b"all quiet\n", None)

    assert failed.value.reason == "all quiet (exit code 3)"


@pytest.mark.unit
def test_a_request_needs_at_least_one_target_file():
    with pytest.raises(ValueError, match="target file"):
        MeasureRequest(cwd="/p", pytest_args=(), target_files=(), scratch_dir="/s")
