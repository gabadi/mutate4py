"""Unit tests for acceptance/steps/nested_pytest_helpers.py."""

import pytest

from acceptance.steps.nested_pytest_helpers import nested_pytest_env


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
def test_autoload_on_removes_the_switch_and_the_plugin_flags():
    base = {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTEST_ADDOPTS": "-p pytest_cov", "PATH": "/bin"}

    assert nested_pytest_env(base, autoload=True) == {"PATH": "/bin"}


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
