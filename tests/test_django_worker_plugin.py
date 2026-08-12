"""Unit tests for _django_worker_plugin.py (issue 05)."""

import types

from mutate4py._django_worker_plugin import pytest_configure
import pytest


def _fake_config():
    return types.SimpleNamespace()


@pytest.mark.unit
def test_pytest_configure_sets_workerinput_from_env(monkeypatch):
    monkeypatch.setenv("MUTATE4PY_WORKER_ID", "gw1")
    config = _fake_config()
    pytest_configure(config)
    assert config.workerinput == {"workerid": "gw1"}


@pytest.mark.unit
def test_pytest_configure_is_noop_without_env(monkeypatch):
    monkeypatch.delenv("MUTATE4PY_WORKER_ID", raising=False)
    config = _fake_config()
    pytest_configure(config)
    assert not hasattr(config, "workerinput")


@pytest.mark.unit
def test_pytest_configure_is_noop_on_empty_env(monkeypatch):
    monkeypatch.setenv("MUTATE4PY_WORKER_ID", "")
    config = _fake_config()
    pytest_configure(config)
    assert not hasattr(config, "workerinput")


@pytest.mark.unit
def test_pytest_configure_never_overwrites_a_real_xdist_workerinput(monkeypatch):
    """A user routing -n auto through --pytest-args already has a real
    xdist workerinput; it must win over this plugin's synthetic one."""
    monkeypatch.setenv("MUTATE4PY_WORKER_ID", "gw1")
    config = _fake_config()
    config.workerinput = {"workerid": "real-xdist-worker"}
    pytest_configure(config)
    assert config.workerinput == {"workerid": "real-xdist-worker"}
