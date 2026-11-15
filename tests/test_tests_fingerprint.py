"""Unit tests for _tests_fingerprint.py (design 89 §5b): the skip predicate and the fingerprint."""

import dataclasses
import importlib.metadata
import shlex
import sys

import pytest

from mutate4py._digest_inputs import digest_inputs_from
from mutate4py._manifest import embed_manifest
from mutate4py._tests_fingerprint import TargetFacts, can_skip_measurement, fingerprint_inputs
from mutate4py._pytest_inifile import last_option_value, option_values
from mutate4py._tests_fingerprint import tests_fingerprint as fingerprint_of

FRESH = "fresh-fingerprint"


def _passing(**overrides: object) -> TargetFacts:
    facts = TargetFacts(
        manifest_fingerprint=FRESH,
        source_unchanged=True,
        fully_scored=True,
        accepted_markers_intact=True,
    )
    return dataclasses.replace(facts, **overrides)


@pytest.mark.unit
def test_skips_when_every_condition_holds_for_every_target():
    assert can_skip_measurement([_passing(), _passing()], FRESH) is True


@pytest.mark.unit
def test_no_targets_never_skip():
    assert can_skip_measurement([], FRESH) is False


@pytest.mark.unit
@pytest.mark.parametrize(
    "override",
    [
        pytest.param({"manifest_fingerprint": None}, id="no-manifest-or-no-fingerprint"),
        pytest.param({"manifest_fingerprint": "older-run"}, id="fingerprint-differs"),
        pytest.param({"source_unchanged": False}, id="source-changed"),
        pytest.param({"fully_scored": False}, id="unscored-or-digestless-function"),
        pytest.param({"accepted_markers_intact": False}, id="accepted-marker-lost"),
    ],
)
def test_each_condition_alone_blocks_the_skip(override):
    assert can_skip_measurement([_passing(**override)], FRESH) is False


@pytest.mark.unit
def test_one_failing_target_blocks_the_skip_for_the_whole_run():
    targets = [_passing(), _passing(source_unchanged=False)]
    assert can_skip_measurement(targets, FRESH) is False


@pytest.mark.unit
def test_a_run_with_no_targets_does_not_skip():
    assert can_skip_measurement([], FRESH) is False


def _project(root) -> str:
    """A small project: pytest.ini at the root, one test file, one source file, a lockfile."""
    (root / "tests").mkdir()
    (root / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n")
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("VALUE = 1\n")
    (root / "pytest.ini").write_text("[pytest]\n")
    (root / "uv.lock").write_text("version = 1\n")
    return str(root)


@pytest.mark.unit
def test_identical_inputs_give_the_same_fingerprint(tmp_path):
    root = _project(tmp_path)
    assert fingerprint_of(root, "") == fingerprint_of(root, "")


@pytest.mark.unit
def test_editing_a_test_file_changes_it(tmp_path):
    root = _project(tmp_path)
    before = fingerprint_of(root, "")
    (tmp_path / "tests" / "test_a.py").write_text("def test_a():\n    assert 1 == 1\n")
    assert fingerprint_of(root, "") != before


@pytest.mark.unit
def test_adding_a_test_file_changes_it(tmp_path):
    root = _project(tmp_path)
    before = fingerprint_of(root, "")
    (tmp_path / "tests" / "test_b.py").write_text("def test_b():\n    assert True\n")
    assert fingerprint_of(root, "") != before


@pytest.mark.unit
def test_deleting_a_test_file_changes_it(tmp_path):
    root = _project(tmp_path)
    before = fingerprint_of(root, "")
    (tmp_path / "tests" / "test_a.py").unlink()
    assert fingerprint_of(root, "") != before


@pytest.mark.unit
def test_renaming_a_test_file_changes_it_even_with_the_same_content(tmp_path):
    root = _project(tmp_path)
    before = fingerprint_of(root, "")
    (tmp_path / "tests" / "test_a.py").rename(tmp_path / "tests" / "test_renamed.py")
    assert fingerprint_of(root, "") != before


@pytest.mark.unit
def test_editing_a_file_outside_the_positional_roots_does_not_change_it(tmp_path):
    root = _project(tmp_path)
    before = fingerprint_of(root, "tests")
    (tmp_path / "src" / "app.py").write_text("VALUE = 2\n")
    assert fingerprint_of(root, "tests") == before


@pytest.mark.unit
def test_editing_a_file_under_the_positional_root_changes_it(tmp_path):
    root = _project(tmp_path)
    before = fingerprint_of(root, "tests")
    (tmp_path / "tests" / "test_a.py").write_text("def test_a():\n    assert 1 == 1\n")
    assert fingerprint_of(root, "tests") != before


@pytest.mark.unit
def test_a_nodeid_argument_narrows_the_walk_to_its_file(tmp_path):
    root = _project(tmp_path)
    before = fingerprint_of(root, "tests/test_a.py::test_a")
    (tmp_path / "src" / "app.py").write_text("VALUE = 2\n")
    assert fingerprint_of(root, "tests/test_a.py::test_a") == before


@pytest.mark.unit
def test_editing_a_file_outside_the_configured_testpaths_does_not_change_it(tmp_path):
    root = _project(tmp_path)
    (tmp_path / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n")
    before = fingerprint_of(root, "")
    (tmp_path / "src" / "app.py").write_text("VALUE = 2\n")
    assert fingerprint_of(root, "") == before


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "text"),
    [
        pytest.param("pyproject.toml", '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n', id="pyproject"),
        pytest.param("tox.ini", "[pytest]\ntestpaths = tests\n", id="tox-ini"),
        pytest.param("setup.cfg", "[tool:pytest]\ntestpaths = tests\n", id="setup-cfg"),
    ],
)
def test_testpaths_in_any_pytest_config_file_narrow_the_walk(tmp_path, name, text):
    root = _project(tmp_path)
    (tmp_path / "pytest.ini").unlink()
    (tmp_path / name).write_text(text)
    before = fingerprint_of(root, "")
    (tmp_path / "src" / "app.py").write_text("VALUE = 2\n")
    assert fingerprint_of(root, "") == before


@pytest.mark.unit
def test_a_pytest_ini_without_testpaths_wins_over_a_pyproject_testpaths(tmp_path):
    root = _project(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
    before = fingerprint_of(root, "")
    (tmp_path / "src" / "app.py").write_text("VALUE = 2\n")
    assert fingerprint_of(root, "") != before


@pytest.mark.unit
def test_a_testpaths_glob_is_expanded_so_its_matches_are_hashed(tmp_path):
    root = _project(tmp_path)
    (tmp_path / "pytest.ini").write_text("[pytest]\ntestpaths = tests/*\n")
    before = fingerprint_of(root, "")
    (tmp_path / "tests" / "test_a.py").write_text("def test_a():\n    assert 1 == 1\n")
    assert fingerprint_of(root, "") != before


@pytest.mark.unit
def test_a_testpaths_glob_matching_nothing_widens_to_the_run_directory(tmp_path):
    root = _project(tmp_path)
    (tmp_path / "pytest.ini").write_text("[pytest]\ntestpaths = nowhere/*\n")
    before = fingerprint_of(root, "")
    (tmp_path / "src" / "app.py").write_text("VALUE = 2\n")
    assert fingerprint_of(root, "") != before


@pytest.mark.unit
def test_missing_testpaths_widens_to_the_run_directory(tmp_path):
    root = _project(tmp_path)
    before = fingerprint_of(root, "")
    (tmp_path / "src" / "app.py").write_text("VALUE = 2\n")
    assert fingerprint_of(root, "") != before


@pytest.mark.unit
def test_editing_a_conftest_above_the_root_changes_it(tmp_path):
    root = _project(tmp_path)
    (tmp_path / "conftest.py").write_text("SHARED = 1\n")
    before = fingerprint_of(root, "tests")
    (tmp_path / "conftest.py").write_text("SHARED = 2\n")
    assert fingerprint_of(root, "tests") != before


@pytest.mark.unit
def test_adding_a_conftest_above_the_root_changes_it(tmp_path):
    root = _project(tmp_path)
    before = fingerprint_of(root, "tests")
    (tmp_path / "conftest.py").write_text("SHARED = 1\n")
    assert fingerprint_of(root, "tests") != before


@pytest.mark.unit
def test_editing_the_pytest_ini_changes_it(tmp_path):
    root = _project(tmp_path)
    before = fingerprint_of(root, "")
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = -q\n")
    assert fingerprint_of(root, "") != before


@pytest.mark.unit
def test_only_the_pytest_table_of_pyproject_counts(tmp_path):
    root = _project(tmp_path)
    (tmp_path / "pytest.ini").unlink()
    pyproject = '[project]\nname = "demo"\nversion = "{version}"\n\n[tool.pytest.ini_options]\naddopts = "{opts}"\n'
    (tmp_path / "pyproject.toml").write_text(pyproject.format(version="1.0", opts="-q"))
    before = fingerprint_of(root, "")
    (tmp_path / "pyproject.toml").write_text(pyproject.format(version="2.0", opts="-q"))
    assert fingerprint_of(root, "") == before
    (tmp_path / "pyproject.toml").write_text(pyproject.format(version="2.0", opts="-x"))
    assert fingerprint_of(root, "") != before


@pytest.mark.unit
def test_the_order_of_keys_in_the_pytest_table_does_not_count(tmp_path):
    root = _project(tmp_path)
    (tmp_path / "pytest.ini").unlink()
    (tmp_path / "pyproject.toml").write_text('[tool.pytest.ini_options]\naddopts = "-q"\nmarkers = ["a"]\n')
    before = fingerprint_of(root, "")
    (tmp_path / "pyproject.toml").write_text('[tool.pytest.ini_options]\nmarkers = ["a"]\naddopts = "-q"\n')
    assert fingerprint_of(root, "") == before


@pytest.mark.unit
def test_an_option_value_is_the_token_after_its_name_and_nothing_before_it():
    assert option_values(["-q", "-c", "conf.ini"], "-c") == ["conf.ini"]
    assert option_values(["-c"], "-c") == []


@pytest.mark.unit
def test_editing_the_lockfile_changes_it(tmp_path):
    root = _project(tmp_path)
    before = fingerprint_of(root, "")
    (tmp_path / "uv.lock").write_text("version = 2\n")
    assert fingerprint_of(root, "") != before


@pytest.mark.unit
def test_changing_the_pytest_args_string_changes_it(tmp_path):
    root = _project(tmp_path)
    assert fingerprint_of(root, "-q") != fingerprint_of(root, "-x")


@pytest.mark.unit
def test_the_python_version_changes_it(tmp_path, monkeypatch):
    root = _project(tmp_path)
    before = fingerprint_of(root, "")
    monkeypatch.setattr(sys, "version", "3.99.0 (test)")
    assert fingerprint_of(root, "") != before


@pytest.mark.unit
def test_the_mutate4py_version_changes_it(tmp_path, monkeypatch):
    root = _project(tmp_path)
    before = fingerprint_of(root, "")
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "9.9.9")
    assert fingerprint_of(root, "") != before


@pytest.mark.unit
def test_a_missing_mutate4py_install_still_fingerprints(tmp_path, monkeypatch):
    root = _project(tmp_path)

    def not_installed(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", not_installed)
    assert isinstance(fingerprint_of(root, ""), str)


@pytest.mark.unit
@pytest.mark.parametrize("name", [".pytest.ini", "pytest.toml", ".pytest.toml", "tox.ini", "setup.cfg"])
def test_editing_another_pytest_config_file_changes_it(tmp_path, name):
    root = _project(tmp_path)
    (tmp_path / name).write_text("[pytest]\n")
    before = fingerprint_of(root, "")
    (tmp_path / name).write_text("[pytest]\naddopts = -q\n")
    assert fingerprint_of(root, "") != before


@pytest.mark.unit
def test_an_unparseable_pyproject_is_hashed_whole(tmp_path):
    root = _project(tmp_path)
    (tmp_path / "pytest.ini").unlink()
    (tmp_path / "pyproject.toml").write_text("[tool.pytest\n")
    before = fingerprint_of(root, "")
    (tmp_path / "pyproject.toml").write_text("[tool.pytest\n# edited\n")
    assert fingerprint_of(root, "") != before


@pytest.mark.unit
def test_a_flag_with_a_separate_value_widens_to_the_whole_root(tmp_path):
    root = _project(tmp_path)
    before = fingerprint_of(root, "-k test_a")
    (tmp_path / "src" / "app.py").write_text("VALUE = 2\n")
    assert fingerprint_of(root, "-k test_a") != before


@pytest.mark.unit
def test_an_unclassified_flag_may_take_the_next_token_so_the_walk_widens(tmp_path):
    root = _project(tmp_path)
    (tmp_path / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n")
    before = fingerprint_of(root, "--some-plugin-flag tests")
    (tmp_path / "src" / "app.py").write_text("VALUE = 2\n")
    assert fingerprint_of(root, "--some-plugin-flag tests") != before


@pytest.mark.unit
@pytest.mark.parametrize(
    "args",
    [
        pytest.param("-p no:cacheprovider -m 'not integration'", id="plugin-and-marker"),
        pytest.param("-k src", id="keyword-value-named-like-a-path"),
    ],
)
def test_value_options_take_their_value_and_keep_the_walk_narrowed(tmp_path, args):
    root = _project(tmp_path)
    (tmp_path / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n")
    before = fingerprint_of(root, args)
    (tmp_path / "src" / "app.py").write_text("VALUE = 2\n")
    assert fingerprint_of(root, args) == before


@pytest.mark.unit
def test_quiet_flags_keep_the_walk_narrowed_to_the_positional_root(tmp_path):
    root = _project(tmp_path)
    before = fingerprint_of(root, "-q tests")
    (tmp_path / "src" / "app.py").write_text("VALUE = 2\n")
    assert fingerprint_of(root, "-q tests") == before


@pytest.mark.unit
def test_unbalanced_quotes_never_match_an_earlier_fingerprint(tmp_path):
    root = _project(tmp_path)
    assert fingerprint_of(root, "-k 'unclosed") != fingerprint_of(root, "-k 'unclosed")


@pytest.mark.unit
def test_a_malformed_pytest_ini_widens_instead_of_failing(tmp_path):
    root = _project(tmp_path)
    (tmp_path / "pytest.ini").write_text("addopts = -q\n")
    before = fingerprint_of(root, "")
    (tmp_path / "src" / "app.py").write_text("VALUE = 2\n")
    assert fingerprint_of(root, "") != before


@pytest.mark.unit
def test_editing_an_explicit_config_file_changes_it(tmp_path):
    root = _project(tmp_path)
    custom = tmp_path / "elsewhere" / "custom.ini"
    custom.parent.mkdir()
    custom.write_text("[pytest]\n")
    args = f"-c {custom}"
    before = fingerprint_of(root, args)
    custom.write_text("[pytest]\naddopts = -q\n")
    assert fingerprint_of(root, args) != before


@pytest.mark.unit
@pytest.mark.parametrize("spelling", ["--config-file {custom}", "--config-file={custom}"])
def test_editing_a_config_file_named_by_config_file_changes_it(tmp_path, spelling):
    root = _project(tmp_path)
    custom = tmp_path / "elsewhere" / "custom.ini"
    custom.parent.mkdir()
    custom.write_text("[pytest]\n")
    args = "tests " + spelling.format(custom=custom)
    before = fingerprint_of(root, args)
    custom.write_text("[pytest]\naddopts = -q\n")
    assert fingerprint_of(root, args) != before


@pytest.mark.unit
def test_editing_the_config_under_an_explicit_rootdir_changes_it(tmp_path):
    root = _project(tmp_path)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "pytest.ini").write_text("[pytest]\n")
    before = fingerprint_of(root, "--rootdir=sub")
    (tmp_path / "sub" / "pytest.ini").write_text("[pytest]\naddopts = -q\n")
    assert fingerprint_of(root, "--rootdir=sub") != before


@pytest.mark.unit
def test_a_config_file_above_the_run_directory_changes_it(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "test_a.py").write_text("def test_a():\n    assert True\n")
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    before = fingerprint_of(str(run), "")
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = -q\n")
    assert fingerprint_of(str(run), "") != before


@pytest.mark.unit
def test_editing_only_a_manifest_footer_does_not_change_it(tmp_path):
    root = _project(tmp_path)
    source = tmp_path / "src" / "app.py"
    source.write_text(embed_manifest("VALUE = 1\n", {"functions": [], "tests_fingerprint": "first"}))
    before = fingerprint_of(root, "")
    source.write_text(embed_manifest("VALUE = 1\n", {"functions": [], "tests_fingerprint": "second"}))
    assert fingerprint_of(root, "") == before


@pytest.mark.unit
def test_every_file_a_digest_reads_is_a_fingerprint_input(digest_project):
    inputs = digest_inputs_from(digest_project.record, reach={})
    named = {*inputs.all_test_files, *inputs.support_files}
    named |= {conftest for conftests in inputs.conftests_for.values() for conftest in conftests}

    listed = fingerprint_inputs(str(digest_project.root), "tests")

    assert sorted(named - set(listed)) == []


def _checkout(parent, name: str) -> str:
    """The same project under `parent/name`."""
    root = parent / name
    root.mkdir(parents=True)
    return _project(root)


@pytest.mark.unit
def test_the_same_project_at_two_depths_gives_the_same_fingerprint(tmp_path):
    shallow = _checkout(tmp_path / "a", "checkout")
    deep = _checkout(tmp_path / "b" / "c" / "d" / "e", "checkout")
    assert fingerprint_inputs(shallow, "tests") == fingerprint_inputs(deep, "tests")
    assert fingerprint_of(shallow, "tests") == fingerprint_of(deep, "tests")


@pytest.mark.unit
def test_an_absent_ancestor_file_is_not_recorded(tmp_path):
    root = _checkout(tmp_path / "a" / "b", "checkout")
    assert "absent" not in fingerprint_inputs(root, "tests").values()
    assert [key for key in fingerprint_inputs(root, "tests") if key.startswith("..")] == []


@pytest.mark.unit
def test_a_conftest_at_the_project_root_changes_a_subdirectory_run(tmp_path):
    _project(tmp_path)
    package = tmp_path / "pkg"
    package.mkdir()
    conftest = tmp_path / "conftest.py"
    conftest.write_text("SHARED = 1\n")
    before = fingerprint_of(str(package), "")
    conftest.write_text("SHARED = 2\n")
    assert fingerprint_of(str(package), "") != before


@pytest.mark.unit
def test_a_superproject_conftest_changes_a_submodule_run(tmp_path):
    superproject = tmp_path / "super"
    superproject.mkdir()
    (superproject / ".git").mkdir()
    conftest = superproject / "conftest.py"
    conftest.write_text("SHARED = 1\n")
    submodule = _checkout(superproject, "sub")
    (superproject / "sub" / "pytest.ini").unlink()
    (superproject / "sub" / ".git").write_text("gitdir: ../.git/modules/sub\n")
    before = fingerprint_of(submodule, "tests")
    conftest.write_text("SHARED = 2\n")
    assert fingerprint_of(submodule, "tests") != before


@pytest.mark.unit
@pytest.mark.parametrize("name", ["pytest.ini", ".pytest.ini", "pytest.toml", ".pytest.toml", "tox.ini", "setup.cfg"])
def test_creating_a_config_file_in_an_ancestor_changes_it(tmp_path, name):
    root = _checkout(tmp_path, "checkout")
    (tmp_path / "checkout" / "pytest.ini").unlink()
    before = fingerprint_of(root, "tests")
    (tmp_path / name).write_text("[pytest]\n")
    created = fingerprint_of(root, "tests")
    assert created != before
    (tmp_path / name).unlink()
    assert fingerprint_of(root, "tests") == before


@pytest.mark.unit
def test_creating_a_pyproject_in_an_ancestor_changes_it(tmp_path):
    root = _checkout(tmp_path, "checkout")
    (tmp_path / "checkout" / "pytest.ini").unlink()
    before = fingerprint_of(root, "tests")
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\naddopts = '-q'\n")
    assert fingerprint_of(root, "tests") != before


def _outer_checkout(tmp_path):
    """An outer checkout whose pyproject.toml has a pytest table and which has its own conftest."""
    outer = tmp_path / "outer"
    outer.mkdir()
    (outer / "pyproject.toml").write_text("[tool.pytest.ini_options]\naddopts = '-q'\n")
    (outer / "conftest.py").write_text("OUTER = 1\n")
    return outer


@pytest.mark.unit
@pytest.mark.parametrize("layout", [".claude/worktrees/x", ".worktrees/coder"])
def test_a_worktree_nested_under_an_outer_checkout_matches_the_standalone_project(tmp_path, layout):
    standalone = _checkout(tmp_path / "alone", "project")
    nested = _checkout(_outer_checkout(tmp_path) / layout, "project")
    assert fingerprint_inputs(nested, "tests") == fingerprint_inputs(standalone, "tests")
    assert fingerprint_of(nested, "tests") == fingerprint_of(standalone, "tests")


@pytest.mark.unit
def test_editing_the_outer_checkout_does_not_change_a_nested_worktree(tmp_path):
    outer = _outer_checkout(tmp_path)
    nested = _checkout(outer / ".worktrees" / "coder", "project")
    before = fingerprint_of(nested, "tests")
    (outer / "conftest.py").write_text("OUTER = 2\n")
    (outer / "pyproject.toml").write_text("[tool.pytest.ini_options]\naddopts = '-x'\n")
    assert fingerprint_of(nested, "tests") == before


@pytest.mark.unit
def test_a_conftest_above_the_inifile_directory_does_not_change_it(tmp_path):
    root = _checkout(tmp_path, "checkout")
    (tmp_path / "conftest.py").write_text("SHARED = 1\n")
    before = fingerprint_of(root, "tests")
    (tmp_path / "conftest.py").write_text("SHARED = 2\n")
    assert fingerprint_of(root, "tests") == before


@pytest.mark.unit
def test_a_conftest_in_the_inifile_directory_still_changes_it(tmp_path):
    root = _checkout(tmp_path, "checkout")
    conftest = tmp_path / "checkout" / "conftest.py"
    conftest.write_text("SHARED = 1\n")
    before = fingerprint_of(root, "tests")
    conftest.write_text("SHARED = 2\n")
    assert fingerprint_of(root, "tests") != before


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "text"),
    [
        pytest.param("pytest.ini", "", id="pytest-ini-even-empty"),
        pytest.param(".pytest.ini", "", id="dot-pytest-ini-even-empty"),
        pytest.param("pytest.toml", "", id="pytest-toml-even-empty"),
        pytest.param(".pytest.toml", "", id="dot-pytest-toml-even-empty"),
        pytest.param("pyproject.toml", "[tool.pytest.ini_options]\n", id="pyproject-ini-options"),
        pytest.param("pyproject.toml", "[tool.pytest]\naddopts = ['-q']\n", id="pyproject-native-table"),
        pytest.param("tox.ini", "[pytest]\n", id="tox-ini-pytest-section"),
        pytest.param("setup.cfg", "[tool:pytest]\n", id="setup-cfg-tool-pytest-section"),
    ],
)
def test_a_file_pytest_accepts_as_its_inifile_ends_the_walk(tmp_path, name, text):
    root = _checkout(tmp_path / "up", "checkout")
    (tmp_path / "up" / "checkout" / "pytest.ini").unlink()
    (tmp_path / "up" / "checkout" / name).write_text(text)
    (tmp_path / "conftest.py").write_text("SHARED = 1\n")
    before = fingerprint_of(root, "tests")
    (tmp_path / "conftest.py").write_text("SHARED = 2\n")
    assert fingerprint_of(root, "tests") == before


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "text"),
    [
        pytest.param("tox.ini", "[tox]\n", id="tox-ini-without-pytest-section"),
        pytest.param("tox.ini", "[pytest\n", id="tox-ini-that-does-not-parse"),
        pytest.param("setup.cfg", "[tool:pytest\n", id="setup-cfg-that-does-not-parse"),
        pytest.param("setup.cfg", "[metadata]\nname = demo\n", id="setup-cfg-without-tool-pytest"),
        pytest.param("setup.cfg", "[pytest]\n", id="setup-cfg-plain-pytest-section"),
        pytest.param("pyproject.toml", "[tool.pytest]\n", id="pyproject-empty-pytest-table"),
        pytest.param("pyproject.toml", "[tool.other]\nx = 1\n", id="pyproject-without-pytest-table"),
        pytest.param("pyproject.toml", "[tool.pytest\n", id="pyproject-that-does-not-parse"),
    ],
)
def test_a_file_pytest_does_not_accept_as_its_inifile_does_not_end_the_walk(tmp_path, name, text):
    root = _checkout(tmp_path / "up", "checkout")
    (tmp_path / "up" / "checkout" / "pytest.ini").unlink()
    (tmp_path / "up" / "checkout" / name).write_text(text)
    (tmp_path / "up" / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "up" / "conftest.py").write_text("SHARED = 1\n")
    before = fingerprint_of(root, "tests")
    (tmp_path / "up" / "conftest.py").write_text("SHARED = 2\n")
    assert fingerprint_of(root, "tests") != before


@pytest.mark.unit
def test_a_pyproject_without_a_pytest_table_is_the_inifile_only_when_no_other_inifile_exists(tmp_path):
    root = _checkout(tmp_path / "up", "checkout")
    (tmp_path / "up" / "checkout" / "pytest.ini").unlink()
    (tmp_path / "up" / "checkout" / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    (tmp_path / "up" / "conftest.py").write_text("SHARED = 1\n")
    before = fingerprint_of(root, "tests")
    (tmp_path / "up" / "conftest.py").write_text("SHARED = 2\n")
    assert fingerprint_of(root, "tests") == before


@pytest.mark.unit
def test_with_no_inifile_anywhere_the_walk_reaches_the_filesystem_root(tmp_path):
    root = _checkout(tmp_path / "a" / "b", "checkout")
    (tmp_path / "a" / "b" / "checkout" / "pytest.ini").unlink()
    (tmp_path / "conftest.py").write_text("SHARED = 1\n")
    before = fingerprint_of(root, "tests")
    (tmp_path / "conftest.py").write_text("SHARED = 2\n")
    assert fingerprint_of(root, "tests") != before


@pytest.mark.unit
def test_an_explicit_config_file_ends_the_walk_at_its_directory(tmp_path):
    base = tmp_path / "base"
    root = _checkout(base, "checkout")
    (base / "checkout" / "pytest.ini").unlink()
    (base / "custom.ini").write_text("[pytest]\n")
    (tmp_path / "conftest.py").write_text("SHARED = 1\n")
    (base / "pyproject.toml").write_text("[tool.pytest.ini_options]\naddopts = '-q'\n")
    args = "-c ../custom.ini tests"
    before = fingerprint_of(root, args)
    (tmp_path / "conftest.py").write_text("SHARED = 2\n")
    (base / "pyproject.toml").write_text("[tool.pytest.ini_options]\naddopts = '-x'\n")
    assert fingerprint_of(root, args) == before
    (base / "conftest.py").write_text("SHARED = 1\n")
    assert fingerprint_of(root, args) != before


@pytest.mark.unit
@pytest.mark.parametrize("spelling", ["--config-file ../custom.ini", "--config-file=../custom.ini"])
def test_config_file_ends_the_walk_at_its_directory_like_c(tmp_path, spelling):
    base = tmp_path / "base"
    root = _checkout(base, "checkout")
    (base / "checkout" / "pytest.ini").unlink()
    (base / "custom.ini").write_text("[pytest]\n")
    (tmp_path / "conftest.py").write_text("SHARED = 1\n")
    (base / "pyproject.toml").write_text("[tool.pytest.ini_options]\naddopts = '-q'\n")
    args = f"{spelling} tests"
    before = fingerprint_of(root, args)
    (tmp_path / "conftest.py").write_text("SHARED = 2\n")
    (base / "pyproject.toml").write_text("[tool.pytest.ini_options]\naddopts = '-x'\n")
    assert fingerprint_of(root, args) == before
    (base / "conftest.py").write_text("SHARED = 1\n")
    assert fingerprint_of(root, args) != before


@pytest.mark.unit
def test_the_last_config_file_option_sets_the_bound_whichever_spelling_it_uses(tmp_path):
    base = tmp_path / "base"
    root = _checkout(base, "checkout")
    (base / "checkout" / "pytest.ini").unlink()
    (base / "custom.ini").write_text("[pytest]\n")
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "x.ini").write_text("[pytest]\n")
    args = f"-c {tmp_path}/other/x.ini --config-file=../custom.ini tests"
    assert option_values(shlex.split(args), "-c", "--config-file")[-1] == "../custom.ini"
    assert last_option_value(shlex.split(args), "-c", "--config-file") == "../custom.ini"
    (tmp_path / "conftest.py").write_text("SHARED = 1\n")
    before = fingerprint_of(root, args)
    (tmp_path / "conftest.py").write_text("SHARED = 2\n")
    assert fingerprint_of(root, args) == before
    (base / "conftest.py").write_text("SHARED = 1\n")
    assert fingerprint_of(root, args) != before


@pytest.mark.unit
@pytest.mark.parametrize("spelling", ["--confcutdir={base}", "--confcutdir {base}"])
def test_confcutdir_ends_the_conftest_walk_at_its_directory(tmp_path, spelling):
    base = tmp_path / "base"
    root = _checkout(base, "checkout")
    (base / "checkout" / "pytest.ini").unlink()
    (tmp_path / "conftest.py").write_text("SHARED = 1\n")
    args = "tests " + spelling.format(base=base)
    before = fingerprint_of(root, args)
    (tmp_path / "conftest.py").write_text("SHARED = 2\n")
    assert fingerprint_of(root, args) == before
    (base / "conftest.py").write_text("SHARED = 1\n")
    assert fingerprint_of(root, args) != before


@pytest.mark.unit
def test_rootdir_ends_the_conftest_walk_when_no_inifile_exists(tmp_path):
    base = tmp_path / "base"
    root = _checkout(base, "checkout")
    (base / "checkout" / "pytest.ini").unlink()
    (tmp_path / "conftest.py").write_text("SHARED = 1\n")
    args = f"tests --rootdir={base}"
    before = fingerprint_of(root, args)
    (tmp_path / "conftest.py").write_text("SHARED = 2\n")
    assert fingerprint_of(root, args) == before
    (base / "conftest.py").write_text("SHARED = 1\n")
    assert fingerprint_of(root, args) != before


@pytest.mark.unit
def test_an_ini_file_that_is_not_text_is_not_an_inifile(tmp_path):
    root = _checkout(tmp_path / "up", "checkout")
    (tmp_path / "up" / "checkout" / "pytest.ini").unlink()
    (tmp_path / "up" / "checkout" / "tox.ini").write_bytes(b"\xff[pytest]\n")
    (tmp_path / "up" / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "up" / "conftest.py").write_text("SHARED = 1\n")
    before = fingerprint_of(root, "tests")
    (tmp_path / "up" / "conftest.py").write_text("SHARED = 2\n")
    assert fingerprint_of(root, "tests") != before


@pytest.mark.unit
@pytest.mark.parametrize(
    "table",
    [
        pytest.param("[tool.pytest.ini_options]\naddopts = '-q'\n", id="ini-options"),
        pytest.param("[tool.pytest]\naddopts = ['-q']\n", id="native-table"),
    ],
)
def test_a_pyproject_with_a_pytest_table_ends_the_walk_past_a_nearer_one_without(tmp_path, table):
    checkout = tmp_path / "up" / "checkout"
    package = checkout / "pkg"
    package.mkdir(parents=True)
    (package / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    (checkout / "pyproject.toml").write_text(table)
    (checkout / "conftest.py").write_text("SHARED = 1\n")
    (tmp_path / "conftest.py").write_text("OUTER = 1\n")
    before = fingerprint_of(str(package), "")
    (tmp_path / "conftest.py").write_text("OUTER = 2\n")
    assert fingerprint_of(str(package), "") == before
    (checkout / "conftest.py").write_text("SHARED = 2\n")
    assert fingerprint_of(str(package), "") != before


@pytest.mark.unit
def test_option_values_reads_every_name_in_argv_order():
    tokens = ["-c", "a.ini", "-q", "--config-file=b.ini", "--config-file", "c.ini", "-cd.ini"]
    assert option_values(tokens, "-c", "--config-file") == ["a.ini", "b.ini", "c.ini", "d.ini"]
    assert option_values(["--config-file"], "-c", "--config-file") == []
