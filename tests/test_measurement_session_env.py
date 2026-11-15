"""The environment the Measurement session runs in, and which fixture setups a test file can pay for."""

import pytest

from mutate4py._measure_record import FixtureSetup
from mutate4py._measurement import _payable, _session_env


@pytest.mark.unit
def test_the_session_env_drops_coverage_hooks_keeps_the_rest_and_forces_ctrace(monkeypatch):
    for name in ("COVERAGE_PROCESS_START", "COVERAGE_RCFILE", "COV_CORE_SOURCE", "COV_CORE_DATAFILE"):
        monkeypatch.setenv(name, "x")
    monkeypatch.setenv("KEEP_ME", "yes")
    monkeypatch.setenv("COVERAGE_CORE", "sysmon")

    env = _session_env()

    assert env["KEEP_ME"] == "yes"
    assert env["COVERAGE_CORE"] == "ctrace"
    assert not {"COVERAGE_PROCESS_START", "COVERAGE_RCFILE", "COV_CORE_SOURCE", "COV_CORE_DATAFILE"} & set(env)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("scope", "setup_file", "requested", "expected"),
    [
        ("function", "tests/test_a.py", set(), True),
        ("function", "tests/test_b.py", {"fix"}, False),
        ("session", "tests/test_b.py", {"fix"}, True),
        ("package", "tests/test_b.py", {"fix"}, True),
        ("session", "tests/test_b.py", {"other"}, False),
        ("module", "tests/test_b.py", {"fix"}, False),
    ],
)
def test_a_setup_is_payable_by_its_own_file_or_by_a_shared_scope_fixture_the_file_requests(
    scope, setup_file, requested, expected
):
    assert _payable(FixtureSetup("fix", scope, 1.0, setup_file), "tests/test_a.py", requested) is expected
