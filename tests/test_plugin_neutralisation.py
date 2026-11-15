"""Unit tests for _plugin_neutralisation.py: the decision table of which kill switches a run keeps.

A switch is dropped only when the child pytest provably does not load its plugin (ADR 0020, amended,
#127): autoload is off and no source names the plugin, or `-p no:<entry point>` blocks it. Every other
case keeps the switch, so a source this module cannot read ends in a loud exit 4, never in a silent
wrong score. Each test builds a throwaway project in `tmp_path`; the inifile there bounds the conftest
search to the project.
"""

import dataclasses
import os
import stat

import pytest

from mutate4py._plugin_neutralisation import _Plugin, neutralising_args

_COV = "--no-cov"
_BENCH = "--benchmark-disable"
_BOTH = ("pytest_cov", "pytest_benchmark")
_AUTOLOAD_ON: dict[str, str] = {}
_AUTOLOAD_OFF = {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}


def _importable(*names):
    return lambda name: object() if name in names else None


@pytest.fixture
def project(tmp_path):
    """A project directory whose inifile is `pytest.ini` with no options."""
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    return tmp_path


def _ask(project, args=(), env=None, importable=_BOTH):
    return neutralising_args(list(args), _importable(*importable), {} if env is None else env, str(project))


def _ini(project, addopts, name="pytest.ini", section="pytest"):
    (project / name).write_text(f"[{section}]\naddopts = {addopts}\n")


# -- importability --------------------------------------------------------------


@pytest.mark.unit
def test_no_known_plugins_importable_returns_empty(project):
    assert _ask(project, importable=()) == []


@pytest.mark.unit
def test_pytest_cov_importable_adds_no_cov(project):
    assert _ask(project, importable=("pytest_cov",)) == [_COV]


@pytest.mark.unit
def test_pytest_benchmark_importable_adds_benchmark_disable(project):
    assert _ask(project, importable=("pytest_benchmark",)) == [_BENCH]


@pytest.mark.unit
def test_both_importable_adds_both_flags_in_table_order(project):
    assert _ask(project) == [_COV, _BENCH]


@pytest.mark.unit
def test_unknown_plugin_importability_never_consulted(project):
    """Only the known plugin modules are ever asked about."""
    seen = []

    def _is_importable(name):
        seen.append(name)
        return None

    neutralising_args([], _is_importable, {}, str(project))
    assert set(seen) == {"pytest_cov", "pytest_benchmark"}


@pytest.mark.unit
def test_default_reflects_this_projects_own_dev_dependencies(project):
    """This project's pyproject.toml pins pytest-cov as a dev dependency and does not pin pytest-benchmark:
    a repo-level fact, so it is safe to assert against the real default importability."""
    args = neutralising_args(environ={}, cwd=str(project))
    assert _COV in args
    assert _BENCH not in args


@pytest.mark.unit
def test_an_importable_plugin_that_is_named_but_not_importable_here_adds_nothing(project):
    assert _ask(project, ["-p", "pytest_cov"], _AUTOLOAD_OFF, importable=()) == []


# -- autoload on ----------------------------------------------------------------


@pytest.mark.unit
def test_autoload_on_keeps_both_switches_whatever_the_args_name(project):
    assert _ask(project, ["-p", "xdist"], _AUTOLOAD_ON) == [_COV, _BENCH]


@pytest.mark.unit
def test_an_empty_autoload_switch_counts_as_autoload_on(project):
    assert _ask(project, env={"PYTEST_DISABLE_PLUGIN_AUTOLOAD": ""}) == [_COV, _BENCH]


@pytest.mark.unit
def test_a_zero_autoload_switch_counts_as_autoload_off_as_pytest_reads_it(project):
    assert _ask(project, env={"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "0"}) == []


# -- autoload off, nothing names the plugin: the switch goes --------------------


@pytest.mark.unit
def test_autoload_off_and_no_source_naming_a_plugin_drops_both_switches(project):
    assert _ask(project, ["-q", "tests"], _AUTOLOAD_OFF) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "pytest_args",
    [["-p", "xdist"], ["-p", "pytest_cover"], ["-p", "pytest_covx.plugin"], ["--pytest_cov"], ["pytest_cov"], ["-p"]],
)
def test_autoload_off_and_another_plugin_or_a_lookalike_named_drops_the_switch(project, pytest_args):
    assert _ask(project, pytest_args, _AUTOLOAD_OFF, importable=("pytest_cov",)) == []


@pytest.mark.unit
def test_autoload_off_with_a_dash_p_whose_value_is_the_next_flag_names_nothing(project):
    assert _ask(project, ["-x", "-p", "-q", "pytest_cov"], _AUTOLOAD_OFF, importable=("pytest_cov",)) == []


@pytest.mark.unit
def test_autoload_off_and_a_different_plugin_in_addopts_drops_the_switch(project):
    assert _ask(project, [], {**_AUTOLOAD_OFF, "PYTEST_ADDOPTS": "-q -p xdist"}) == []


@pytest.mark.unit
def test_naming_one_plugin_keeps_only_its_own_switch(project):
    assert _ask(project, ["-p", "pytest_cov"], _AUTOLOAD_OFF) == [_COV]
    assert _ask(project, ["-p", "benchmark"], _AUTOLOAD_OFF) == [_BENCH]


# -- autoload off, a source names the plugin: the switch stays ------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("pytest_args", "kept"),
    [
        (["-p", "pytest_cov"], _COV),
        (["-ppytest_cov"], _COV),
        (["-p", "pytest_cov.plugin"], _COV),
        (["-ppytest_cov.plugin"], _COV),
        (["-q", "-p", "xdist", "-p", "pytest_cov", "tests"], _COV),
        (["-p", "benchmark"], _BENCH),
        (["-pbenchmark"], _BENCH),
        (["-p", "pytest_benchmark.plugin"], _BENCH),
    ],
)
def test_autoload_off_but_the_plugin_named_in_the_session_args_keeps_its_switch(project, pytest_args, kept):
    assert _ask(project, pytest_args, _AUTOLOAD_OFF) == [kept]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("addopts", "kept"),
    [
        ("-p pytest_cov", _COV),
        ("-ppytest_cov", _COV),
        ("-q -p pytest_cov.plugin", _COV),
        ("--tb=short '-p' pytest_cov", _COV),
        ("-p benchmark", _BENCH),
    ],
)
def test_autoload_off_but_the_plugin_named_in_pytest_addopts_keeps_its_switch(project, addopts, kept):
    assert _ask(project, [], {**_AUTOLOAD_OFF, "PYTEST_ADDOPTS": addopts}) == [kept]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("plugins", "kept"),
    [
        ("pytest_cov", _COV),
        ("xdist, pytest_cov.plugin", _COV),
        ("benchmark", _BENCH),
        ("pytest_benchmark.plugin,x", _BENCH),
    ],
)
def test_autoload_off_but_the_plugin_named_in_pytest_plugins_keeps_its_switch(project, plugins, kept):
    assert _ask(project, [], {**_AUTOLOAD_OFF, "PYTEST_PLUGINS": plugins}) == [kept]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "section"),
    [("pytest.ini", "pytest"), (".pytest.ini", "pytest"), ("tox.ini", "pytest"), ("setup.cfg", "tool:pytest")],
)
def test_autoload_off_but_the_plugin_named_in_the_inifile_addopts_keeps_its_switch(project, name, section):
    if name != "pytest.ini":
        (project / "pytest.ini").unlink()
    _ini(project, "-p pytest_cov --cov=calc", name, section)
    assert _ask(project, [], _AUTOLOAD_OFF) == [_COV]


@pytest.mark.unit
def test_autoload_off_but_the_plugin_named_in_a_multiline_inifile_addopts_keeps_its_switch(project):
    (project / "pytest.ini").write_text("[pytest]\naddopts =\n    -q\n    -p benchmark\n")
    assert _ask(project, [], _AUTOLOAD_OFF) == [_BENCH]


@pytest.mark.unit
@pytest.mark.parametrize(
    "body",
    [
        '[tool.pytest.ini_options]\naddopts = "-p pytest_cov"\n',
        '[tool.pytest.ini_options]\naddopts = ["-q", "-p", "pytest_cov"]\n',
        '[tool.pytest]\naddopts = ["-ppytest_cov"]\n',
    ],
)
def test_autoload_off_but_the_plugin_named_in_pyproject_addopts_keeps_its_switch(project, body):
    (project / "pytest.ini").unlink()
    (project / "pyproject.toml").write_text(body)
    assert _ask(project, [], _AUTOLOAD_OFF, importable=("pytest_cov",)) == [_COV]


@pytest.mark.unit
def test_autoload_off_but_the_plugin_named_in_a_pytest_toml_keeps_its_switch(project):
    (project / "pytest.ini").unlink()
    (project / "pytest.toml").write_text('[pytest]\naddopts = "-p pytest_cov"\n')
    assert _ask(project, [], _AUTOLOAD_OFF, importable=("pytest_cov",)) == [_COV]


@pytest.mark.unit
def test_the_inifile_is_found_from_the_runs_test_path_as_the_tests_digest_finds_it(project):
    (project / "pytest.ini").unlink()
    (project / "tests").mkdir()
    _ini(project / "tests", "-p pytest_cov")
    assert _ask(project, ["tests"], _AUTOLOAD_OFF, importable=("pytest_cov",)) == [_COV]


@pytest.mark.unit
def test_the_inifile_named_by_dash_c_is_read_and_the_one_in_the_project_is_not(project):
    _ini(project, "-p pytest_cov")
    (project / "other.ini").write_text("[pytest]\n")
    assert _ask(project, ["-c", "other.ini"], _AUTOLOAD_OFF, importable=("pytest_cov",)) == []
    (project / "other.ini").write_text("[pytest]\naddopts = -p pytest_cov\n")
    (project / "pytest.ini").write_text("[pytest]\n")
    assert _ask(project, ["-c", "other.ini"], _AUTOLOAD_OFF, importable=("pytest_cov",)) == [_COV]


@pytest.mark.unit
def test_an_addopts_override_on_the_command_line_names_the_plugin(project):
    assert _ask(project, ["-o", "addopts=-p pytest_cov"], _AUTOLOAD_OFF, importable=("pytest_cov",)) == [_COV]
    assert _ask(project, ["--override-ini=addopts=-p pytest_cov"], _AUTOLOAD_OFF, importable=("pytest_cov",)) == [_COV]


@pytest.mark.unit
def test_an_addopts_override_replaces_the_inifile_addopts(project):
    _ini(project, "-p pytest_cov")
    assert _ask(project, ["-o", "addopts=-q"], _AUTOLOAD_OFF, importable=("pytest_cov",)) == []


@pytest.mark.unit
@pytest.mark.parametrize("tail", ["tests/test_x.py", "tests/sub"])
def test_autoload_off_but_a_conftest_naming_the_plugin_keeps_its_switch(project, tail):
    (project / "tests" / "sub").mkdir(parents=True)
    (project / "tests" / "test_x.py").write_text("")
    (project / "conftest.py").write_text('pytest_plugins = ["pytest_cov"]\n')
    assert _ask(project, [tail], _AUTOLOAD_OFF) == [_COV]


@pytest.mark.unit
def test_autoload_off_but_a_conftest_beneath_the_collection_root_naming_the_plugin_keeps_its_switch(project):
    (project / "tests" / "sub").mkdir(parents=True)
    (project / "tests" / "sub" / "conftest.py").write_text("# uses benchmark\n")
    assert _ask(project, ["tests"], _AUTOLOAD_OFF) == [_BENCH]


@pytest.mark.unit
def test_autoload_off_and_conftests_that_do_not_name_the_plugin_drop_its_switch(project):
    (project / "tests").mkdir()
    (project / "conftest.py").write_text("import os\n")
    (project / "tests" / "conftest.py").write_text("pytest_plugins = ['xdist']\n")
    assert _ask(project, ["tests"], _AUTOLOAD_OFF) == []


@pytest.mark.unit
def test_a_conftest_above_the_inifile_is_not_read(project):
    inner = project / "inner"
    inner.mkdir()
    (inner / "pytest.ini").write_text("[pytest]\n")
    (project / "conftest.py").write_text('pytest_plugins = ["pytest_cov"]\n')
    assert _ask(inner, [], _AUTOLOAD_OFF) == []


@pytest.mark.unit
def test_a_conftest_that_cannot_be_read_keeps_the_switch(project):
    conftest = project / "conftest.py"
    conftest.write_text("")
    conftest.chmod(0)
    try:
        if os.access(conftest, os.R_OK):
            pytest.skip("running as a user that reads any file")
        assert _ask(project, [], _AUTOLOAD_OFF) == [_COV, _BENCH]
    finally:
        conftest.chmod(stat.S_IRUSR | stat.S_IWUSR)


# -- autoload turned off from the args, PYTEST_ADDOPTS or the inifile -----------


@pytest.mark.unit
def test_the_disable_option_in_the_session_args_turns_autoload_off(project):
    assert _ask(project, ["--disable-plugin-autoload", "-q"], _AUTOLOAD_ON) == []


@pytest.mark.unit
def test_the_disable_option_in_pytest_addopts_turns_autoload_off(project):
    assert _ask(project, [], {"PYTEST_ADDOPTS": "-q --disable-plugin-autoload"}) == []


@pytest.mark.unit
def test_the_disable_option_in_the_inifile_addopts_turns_autoload_off(project):
    _ini(project, "-q --disable-plugin-autoload")
    assert _ask(project, [], _AUTOLOAD_ON) == []


@pytest.mark.unit
def test_the_disable_option_in_the_inifile_with_the_plugin_named_there_keeps_the_switch(project):
    _ini(project, "--disable-plugin-autoload -p pytest_cov --cov=calc")
    assert _ask(project, [], _AUTOLOAD_ON) == [_COV]


@pytest.mark.unit
def test_the_disable_option_in_one_of_two_candidate_inifiles_is_not_proof_and_keeps_the_switches(project):
    _ini(project, "--disable-plugin-autoload")
    (project / "tox.ini").write_text("[pytest]\naddopts = -q\n")
    assert _ask(project, [], _AUTOLOAD_ON) == [_COV, _BENCH]


@pytest.mark.unit
def test_the_disable_option_in_an_inifile_that_a_command_line_override_replaces_does_not_count(project):
    _ini(project, "--disable-plugin-autoload")
    assert _ask(project, ["-o", "addopts=-q"], _AUTOLOAD_ON) == [_COV, _BENCH]


@pytest.mark.unit
def test_a_lookalike_of_the_disable_option_does_not_turn_autoload_off(project):
    assert _ask(project, ["--disable-plugin-autoloadx"], _AUTOLOAD_ON) == [_COV, _BENCH]


# -- -p no:<name> ---------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("pytest_args", "dropped"),
    [
        (["-p", "no:pytest_cov"], _COV),
        (["-pno:pytest_cov"], _COV),
        (["-p", "no:benchmark"], _BENCH),
    ],
)
def test_blocking_a_plugin_with_autoload_on_drops_only_its_switch(project, pytest_args, dropped):
    kept = _ask(project, pytest_args, _AUTOLOAD_ON)
    assert kept == [flag for flag in (_COV, _BENCH) if flag != dropped]


@pytest.mark.unit
def test_a_block_in_pytest_addopts_or_the_inifile_addopts_drops_the_switch(project):
    assert _ask(project, [], {"PYTEST_ADDOPTS": "-p no:pytest_cov"}) == [_BENCH]
    _ini(project, "-p no:benchmark")
    assert _ask(project, [], _AUTOLOAD_ON) == [_COV]


@pytest.mark.unit
def test_a_block_does_not_stop_a_plugin_that_another_source_names(project):
    assert _ask(project, ["-p", "no:pytest_cov", "-p", "pytest_cov.plugin"], _AUTOLOAD_ON) == [_COV, _BENCH]


@pytest.mark.unit
def test_a_block_does_not_stop_a_plugin_a_conftest_names(project):
    (project / "conftest.py").write_text('pytest_plugins = ["pytest_cov"]\n')
    assert _ask(project, ["-p", "no:pytest_cov"], _AUTOLOAD_ON) == [_COV, _BENCH]


@pytest.mark.unit
def test_a_block_of_a_lookalike_does_not_drop_the_switch(project):
    assert _ask(project, ["-p", "no:pytest_covx"], _AUTOLOAD_ON) == [_COV, _BENCH]
    assert _ask(project, ["-p", "no:pytest_benchmark"], _AUTOLOAD_ON) == [_COV, _BENCH]


# -- unsure: keep the switch ----------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("addopts", ["-p 'pytest_cov", '-q "unbalanced'])
def test_an_unparsable_pytest_addopts_keeps_every_switch_instead_of_raising(project, addopts):
    assert _ask(project, [], {**_AUTOLOAD_OFF, "PYTEST_ADDOPTS": addopts}) == [_COV, _BENCH]


@pytest.mark.unit
def test_an_unparsable_inifile_addopts_keeps_every_switch_instead_of_raising(project):
    _ini(project, "-q 'unbalanced")
    assert _ask(project, [], _AUTOLOAD_OFF) == [_COV, _BENCH]


@pytest.mark.unit
def test_the_environ_and_the_directory_default_to_the_process_ones(project, monkeypatch):
    monkeypatch.chdir(project)
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    monkeypatch.delenv("PYTEST_PLUGINS", raising=False)
    assert neutralising_args([], _importable(*_BOTH)) == []
    monkeypatch.setenv("PYTEST_ADDOPTS", "-p pytest_cov")
    assert neutralising_args([], _importable(*_BOTH)) == [_COV]
    (project / "conftest.py").write_text("# benchmark\n")
    monkeypatch.delenv("PYTEST_ADDOPTS")
    assert neutralising_args([], _importable(*_BOTH)) == [_BENCH]
    monkeypatch.delenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD")
    assert neutralising_args([], _importable(*_BOTH)) == [_COV, _BENCH]


@pytest.mark.unit
def test_pytest_args_may_be_a_tuple(project):
    assert neutralising_args(("-p", "pytest_cov"), _importable(*_BOTH), _AUTOLOAD_OFF, str(project)) == [_COV]


@pytest.mark.unit
def test_disabled_plugin_args_keeps_only_the_runs_plugin_blocks_in_both_spellings():
    from mutate4py._plugin_neutralisation import disabled_plugin_args

    run_args = ["-q", "-p", "no:tach", "-m", "not slow", "-pno:cacheprovider", "-p", "xdist", "tests"]
    assert disabled_plugin_args(run_args) == ["-p", "no:tach", "-p", "no:cacheprovider"]


@pytest.mark.unit
def test_disabled_plugin_args_ignores_a_trailing_bare_p():
    from mutate4py._plugin_neutralisation import disabled_plugin_args

    assert disabled_plugin_args(["tests", "-p"]) == []


@pytest.mark.unit
def test_a_kill_switch_plugin_cannot_be_changed_after_it_is_built():
    plugin = _Plugin("pytest_cov", "--no-cov", "pytest_cov", ("pytest_cov",))

    with pytest.raises(dataclasses.FrozenInstanceError):
        plugin.module = "other"  # type: ignore[misc]
