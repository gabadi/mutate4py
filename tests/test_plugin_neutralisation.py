"""Unit tests for _plugin_neutralisation.py (issue 06)."""

from mutate4py._plugin_neutralisation import neutralising_args
import pytest


def _importable(*names):
    return lambda name: object() if name in names else None


_AUTOLOAD_ON: dict[str, str] = {}
_AUTOLOAD_OFF = {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}


@pytest.mark.unit
def test_no_known_plugins_importable_returns_empty():
    assert neutralising_args(is_importable=lambda name: None) == []


@pytest.mark.unit
def test_pytest_cov_importable_adds_no_cov():
    args = neutralising_args(is_importable=_importable("pytest_cov"), environ=_AUTOLOAD_ON)
    assert args == ["--no-cov"]


@pytest.mark.unit
def test_pytest_benchmark_importable_adds_benchmark_disable():
    args = neutralising_args(is_importable=lambda name: object() if name == "pytest_benchmark" else None)
    assert args == ["--benchmark-disable"]


@pytest.mark.unit
def test_both_importable_adds_both_flags():
    args = neutralising_args(is_importable=lambda name: object(), environ=_AUTOLOAD_ON)
    assert args == ["--no-cov", "--benchmark-disable"]


@pytest.mark.unit
def test_unknown_plugin_importability_never_consulted():
    """Only the two known plugin names are ever asked about — an importable
    check that flags every OTHER name must not add anything."""
    seen = []

    def _is_importable(name):
        seen.append(name)
        return None

    neutralising_args(is_importable=_is_importable, environ=_AUTOLOAD_ON)
    assert set(seen) == {"pytest_cov", "pytest_benchmark"}


@pytest.mark.unit
def test_default_reflects_this_projects_own_dev_dependencies():
    """This project's own pyproject.toml pins pytest-cov as a dev dependency
    and does not pin pytest-benchmark — a repo-level fact, not a
    machine-dependent one, so it's safe to assert against the real default."""
    args = neutralising_args(environ=_AUTOLOAD_ON)
    assert "--no-cov" in args
    assert "--benchmark-disable" not in args


# ── --no-cov only when the child pytest loads pytest-cov (#127) ───────────


@pytest.mark.unit
def test_autoload_off_and_pytest_cov_not_named_omits_no_cov():
    assert neutralising_args(["-q", "tests"], _importable("pytest_cov"), _AUTOLOAD_OFF) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "pytest_args",
    [
        ["-p", "pytest_cov"],
        ["-ppytest_cov"],
        ["-p", "pytest_cov.plugin"],
        ["-ppytest_cov.plugin"],
        ["-q", "-p", "xdist", "-p", "pytest_cov", "tests"],
    ],
)
def test_autoload_off_but_pytest_cov_named_in_the_pytest_args_adds_no_cov(pytest_args):
    assert neutralising_args(pytest_args, _importable("pytest_cov"), _AUTOLOAD_OFF) == ["--no-cov"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "addopts",
    ["-p pytest_cov", "-ppytest_cov", "-q -p pytest_cov.plugin", "--tb=short '-p' pytest_cov"],
)
def test_autoload_off_but_pytest_cov_named_in_addopts_adds_no_cov(addopts):
    environ = {**_AUTOLOAD_OFF, "PYTEST_ADDOPTS": addopts}
    assert neutralising_args([], _importable("pytest_cov"), environ) == ["--no-cov"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "pytest_args",
    [
        ["-p", "xdist"],
        ["-p", "pytest_cover"],
        ["-p", "pytest_covx.plugin"],
        ["-p", "no:pytest_cov"],
        ["--pytest_cov"],
        ["pytest_cov"],
        ["-p"],
        ["-x", "-p", "-q", "pytest_cov"],
    ],
)
def test_autoload_off_and_another_plugin_or_a_lookalike_named_omits_no_cov(pytest_args):
    assert neutralising_args(pytest_args, _importable("pytest_cov"), _AUTOLOAD_OFF) == []


@pytest.mark.unit
def test_autoload_off_with_an_addopts_that_does_not_name_pytest_cov_omits_no_cov():
    environ = {**_AUTOLOAD_OFF, "PYTEST_ADDOPTS": "-q -p xdist"}
    assert neutralising_args([], _importable("pytest_cov"), environ) == []


@pytest.mark.unit
def test_autoload_off_with_an_unparsable_addopts_omits_no_cov_instead_of_raising():
    environ = {**_AUTOLOAD_OFF, "PYTEST_ADDOPTS": "-p 'pytest_cov"}
    assert neutralising_args([], _importable("pytest_cov"), environ) == []


@pytest.mark.unit
def test_autoload_on_adds_no_cov_whatever_the_args_name():
    assert neutralising_args(["-p", "xdist"], _importable("pytest_cov"), _AUTOLOAD_ON) == ["--no-cov"]


@pytest.mark.unit
def test_an_empty_autoload_switch_counts_as_autoload_on():
    environ = {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": ""}
    assert neutralising_args([], _importable("pytest_cov"), environ) == ["--no-cov"]


@pytest.mark.unit
def test_autoload_off_never_removes_the_benchmark_switch():
    args = neutralising_args([], _importable("pytest_cov", "pytest_benchmark"), _AUTOLOAD_OFF)
    assert args == ["--benchmark-disable"]


@pytest.mark.unit
def test_autoload_off_with_pytest_cov_named_but_not_importable_adds_nothing():
    assert neutralising_args(["-p", "pytest_cov"], _importable(), _AUTOLOAD_OFF) == []


@pytest.mark.unit
def test_the_environ_defaults_to_the_process_environment(monkeypatch):
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    assert neutralising_args([], _importable("pytest_cov")) == []
    monkeypatch.setenv("PYTEST_ADDOPTS", "-p pytest_cov")
    assert neutralising_args([], _importable("pytest_cov")) == ["--no-cov"]
    monkeypatch.delenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD")
    monkeypatch.delenv("PYTEST_ADDOPTS")
    assert neutralising_args([], _importable("pytest_cov")) == ["--no-cov"]


@pytest.mark.unit
def test_disabled_plugin_args_keeps_only_the_runs_plugin_blocks_in_both_spellings():
    from mutate4py._plugin_neutralisation import disabled_plugin_args

    run_args = ["-q", "-p", "no:tach", "-m", "not slow", "-pno:cacheprovider", "-p", "xdist", "tests"]
    assert disabled_plugin_args(run_args) == ["-p", "no:tach", "-p", "no:cacheprovider"]


@pytest.mark.unit
def test_disabled_plugin_args_ignores_a_trailing_bare_p():
    from mutate4py._plugin_neutralisation import disabled_plugin_args

    assert disabled_plugin_args(["tests", "-p"]) == []
