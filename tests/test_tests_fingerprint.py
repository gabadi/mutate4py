"""Unit tests for _tests_fingerprint.py (design 89 §5b): the skip predicate and the fingerprint."""

import dataclasses
import importlib.metadata
import sys

import pytest

from mutate4py._digest_inputs import digest_inputs_from
from mutate4py._manifest import embed_manifest
from mutate4py._tests_fingerprint import TargetFacts, can_skip_measurement, fingerprint_inputs
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
    assert can_skip_measurement([_passing(), _passing()], FRESH, mutate_all=False) is True


@pytest.mark.unit
def test_mutate_all_never_skips():
    assert can_skip_measurement([_passing()], FRESH, mutate_all=True) is False


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
    assert can_skip_measurement([_passing(**override)], FRESH, mutate_all=False) is False


@pytest.mark.unit
def test_one_failing_target_blocks_the_skip_for_the_whole_run():
    targets = [_passing(), _passing(source_unchanged=False)]
    assert can_skip_measurement(targets, FRESH, mutate_all=False) is False


@pytest.mark.unit
def test_a_run_with_no_targets_does_not_skip():
    assert can_skip_measurement([], FRESH, mutate_all=False) is False


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
@pytest.mark.parametrize("name", ["tox.ini", "setup.cfg"])
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
