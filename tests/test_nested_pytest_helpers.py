"""Unit tests for acceptance/steps/nested_pytest_helpers.py."""

import pytest

from acceptance.steps.nested_pytest_helpers import addopts_names_plugin, nested_pytest_env


@pytest.mark.unit
def test_autoload_is_off_and_the_needed_plugin_is_named():
    env = nested_pytest_env({"PATH": "/bin"})

    assert env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert env["PYTEST_ADDOPTS"] == "-p pytest_cov"
    assert env["PATH"] == "/bin"


@pytest.mark.unit
def test_the_callers_own_addopts_are_kept_ahead_of_the_plugin_flags():
    env = nested_pytest_env({"PYTEST_ADDOPTS": "-q"})

    assert env["PYTEST_ADDOPTS"] == "-q -p pytest_cov"


@pytest.mark.unit
def test_an_empty_addopts_adds_no_leading_space():
    assert nested_pytest_env({"PYTEST_ADDOPTS": ""})["PYTEST_ADDOPTS"] == "-p pytest_cov"


@pytest.mark.unit
def test_autoload_on_removes_the_switch_and_keeps_the_callers_addopts():
    base = {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTEST_ADDOPTS": "-q -p pytest_cov", "PATH": "/bin"}

    assert nested_pytest_env(base, autoload=True) == {"PYTEST_ADDOPTS": "-q -p pytest_cov", "PATH": "/bin"}


@pytest.mark.unit
@pytest.mark.parametrize(
    "addopts",
    ["-p pytest_cov", "-ppytest_cov", "-q -p pytest_cov -x", "-p pytest_cov.plugin", "-ppytest_cov.plugin"],
)
def test_addopts_that_already_name_the_plugin_are_not_given_it_twice(addopts):
    env = nested_pytest_env({"PYTEST_ADDOPTS": addopts})

    assert env["PYTEST_ADDOPTS"] == addopts


@pytest.mark.unit
@pytest.mark.parametrize(
    ("addopts", "expected"),
    [
        ("-p pytest_cov", True),
        ("-ppytest_cov", True),
        ("-p pytest_cov.plugin", True),
        ("-p xdist -p pytest_cov", True),
        ("", False),
        ("-q", False),
        ("-p xdist", False),
        ("-p pytest_cover", False),
        ("-p", False),
        ("--no-cov -p pytest_cover.plugin", False),
        ("-k pytest_cov", False),
    ],
)
def test_addopts_names_plugin(addopts, expected):
    assert addopts_names_plugin(addopts, "pytest_cov") is expected


@pytest.mark.unit
def test_the_base_mapping_is_not_modified():
    base = {"PATH": "/bin"}
    nested_pytest_env(base)
    nested_pytest_env(base, autoload=True)

    assert base == {"PATH": "/bin"}


@pytest.mark.unit
def test_the_process_environment_is_the_default_base(monkeypatch):
    monkeypatch.setenv("ACCEPTANCE_PROBE", "x")
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)

    assert nested_pytest_env()["ACCEPTANCE_PROBE"] == "x"


@pytest.mark.system
def test_a_system_test_gets_autoload_off_and_the_plugin_named_once_by_its_entry_point_name():
    """The autouse fixture in tests/conftest.py builds the nested-run environment with the acceptance helper."""
    import os

    assert os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert os.environ["PYTEST_ADDOPTS"].split().count("pytest_cov") == 1
    assert "pytest_cov.plugin" not in os.environ["PYTEST_ADDOPTS"]
