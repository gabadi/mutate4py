"""Unit tests for _plugin_neutralisation.py (issue 06)."""

from mutate4py._plugin_neutralisation import neutralising_args
import pytest


@pytest.mark.unit
def test_no_known_plugins_importable_returns_empty():
    assert neutralising_args(is_importable=lambda name: None) == []


@pytest.mark.unit
def test_pytest_cov_importable_adds_no_cov():
    args = neutralising_args(is_importable=lambda name: object() if name == "pytest_cov" else None)
    assert args == ["--no-cov"]


@pytest.mark.unit
def test_pytest_benchmark_importable_adds_benchmark_disable():
    args = neutralising_args(is_importable=lambda name: object() if name == "pytest_benchmark" else None)
    assert args == ["--benchmark-disable"]


@pytest.mark.unit
def test_both_importable_adds_both_flags():
    args = neutralising_args(is_importable=lambda name: object())
    assert args == ["--no-cov", "--benchmark-disable"]


@pytest.mark.unit
def test_unknown_plugin_importability_never_consulted():
    """Only the two known plugin names are ever asked about — an importable
    check that flags every OTHER name must not add anything."""
    seen = []

    def _is_importable(name):
        seen.append(name)
        return None

    neutralising_args(is_importable=_is_importable)
    assert set(seen) == {"pytest_cov", "pytest_benchmark"}


@pytest.mark.unit
def test_default_reflects_this_projects_own_dev_dependencies():
    """This project's own pyproject.toml pins pytest-cov as a dev dependency
    and does not pin pytest-benchmark — a repo-level fact, not a
    machine-dependent one, so it's safe to assert against the real default."""
    args = neutralising_args()
    assert "--no-cov" in args
    assert "--benchmark-disable" not in args
