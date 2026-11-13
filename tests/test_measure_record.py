"""The Measurement's record format: the pure half of the in-session plugin."""

import pytest

from mutate4py._measure_record import (
    FixtureSetup,
    SessionFacts,
    SessionLog,
    Timing,
    core_from_sys_info,
    dump_record,
    load_record,
)


def _session(**overrides) -> SessionFacts:
    facts = {
        "core": "ctrace",
        "collected": 1,
        "args": ("tests",),
        "rootdir": "/proj",
        "inipath": "/proj/pytest.ini",
        "plugin_files": (),
        "module_files": (),
        "test_files": ("/proj/tests/test_a.py",),
    }
    facts.update(overrides)
    return SessionFacts(**facts)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("tracer", "core"),
    [("CTracer", "ctrace"), ("PyTracer", "pytrace"), ("SysMonitor", "sysmon")],
)
def test_the_effective_core_is_read_from_coverage_sys_info(tracer, core):
    assert core_from_sys_info([("version", "7.13.5"), ("core", tracer)]) == core


@pytest.mark.unit
def test_a_tests_duration_spans_setup_call_and_teardown_with_setup_kept_apart():
    log = SessionLog()
    log.test_started("tests/test_a.py::test_x", ("tmp_path",))
    log.test_phase("tests/test_a.py::test_x", "setup", 0.25, failed=False)
    log.test_phase("tests/test_a.py::test_x", "call", 0.5, failed=False)
    log.test_phase("tests/test_a.py::test_x", "teardown", 0.125, failed=False)

    record = log.finish(_session())

    assert record.tests["tests/test_a.py::test_x"] == Timing(duration=0.875, setup=0.25)
    assert record.failed == ()


@pytest.mark.unit
def test_failing_tests_and_collection_errors_are_named_once_each():
    log = SessionLog()
    log.test_phase("tests/test_a.py::test_x", "setup", 0.0, failed=True)
    log.test_phase("tests/test_a.py::test_x", "teardown", 0.0, failed=True)
    log.test_phase("tests/test_a.py::test_y", "call", 0.0, failed=False)
    log.collection_failed("tests/test_broken.py")

    assert log.finish(_session()).failed == ("tests/test_a.py::test_x", "tests/test_broken.py")


@pytest.mark.unit
def test_a_fixture_setup_is_charged_to_the_file_of_the_test_that_triggered_it():
    log = SessionLog()
    log.test_started("tests/test_a.py::test_x", ("db", "tmp_path"))
    log.fixture_set_up("db", "session", 1.5)
    log.test_started("tests/sub/test_b.py::test_y[1]", ("db",))
    log.fixture_set_up("row", "function", 0.25)

    record = log.finish(_session())

    assert record.fixture_setups == (
        FixtureSetup(fixture="db", scope="session", duration=1.5, test_file="tests/test_a.py"),
        FixtureSetup(fixture="row", scope="function", duration=0.25, test_file="tests/sub/test_b.py"),
    )
    assert record.requested == {
        "tests/test_a.py::test_x": ("db", "tmp_path"),
        "tests/sub/test_b.py::test_y[1]": ("db",),
    }


@pytest.mark.unit
def test_conftests_are_the_registered_plugins_named_conftest():
    facts = _session(plugin_files=("/proj/conftest.py", "/proj/tests/conftest.py", "/venv/pytest_cov/plugin.py"))

    assert SessionLog().finish(facts).conftests == ("/proj/conftest.py", "/proj/tests/conftest.py")


@pytest.mark.unit
def test_support_modules_are_loaded_files_under_a_test_root_other_than_tests_and_conftests():
    facts = _session(
        test_files=("/proj/tests/unit/test_a.py",),
        plugin_files=("/proj/tests/conftest.py",),
        module_files=(
            "/proj/tests/unit/test_a.py",  # a collected test file
            "/proj/tests/conftest.py",  # a conftest
            "/proj/tests/unit/factories.py",  # beside a test file
            "/proj/tests/helpers/builders.py",  # sibling dir under an ancestor root
            "/proj/acceptance/coverage_helpers.py",  # outside every test root
            "/proj/src/pkg/mod.py",  # project code
            "/proj/setup_helpers.py",  # rootdir itself is not a test root
            "/venv/lib/site.py",
        ),
    )

    assert SessionLog().finish(facts).support_modules == (
        "/proj/tests/helpers/builders.py",
        "/proj/tests/unit/factories.py",
    )


@pytest.mark.unit
def test_a_record_survives_its_json_round_trip():
    log = SessionLog()
    log.test_started("tests/test_a.py::test_x", ("db",))
    log.test_phase("tests/test_a.py::test_x", "call", 0.5, failed=True)
    log.fixture_set_up("db", "module", 0.75)
    record = log.finish(_session(plugin_files=("/proj/tests/conftest.py",), module_files=("/proj/tests/factories.py",)))

    assert load_record(dump_record(record)) == record
