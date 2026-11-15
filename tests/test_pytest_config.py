"""Unit tests for _pytest_config.py: the testpaths pytest's configuration declares, read as pytest reads them."""

import pytest

from mutate4py._pytest_config import configured_testpaths


def _dirs(root, *names):
    for name in names:
        (root / name).mkdir(parents=True, exist_ok=True)


@pytest.mark.unit
def test_a_pytest_ini_testpaths_are_read(tmp_path):
    _dirs(tmp_path, "tests")
    (tmp_path / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n")

    assert configured_testpaths(str(tmp_path)) == [str(tmp_path / "tests")]


@pytest.mark.unit
def test_a_pyproject_testpaths_list_is_read_in_the_order_given(tmp_path):
    _dirs(tmp_path, "tests", "extra")
    (tmp_path / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths = ["tests", "extra"]\n')

    assert configured_testpaths(str(tmp_path)) == [str(tmp_path / "tests"), str(tmp_path / "extra")]


@pytest.mark.unit
def test_a_pyproject_testpaths_string_is_read_as_space_separated_patterns(tmp_path):
    _dirs(tmp_path, "tests", "extra")
    (tmp_path / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths = "tests extra"\n')

    assert configured_testpaths(str(tmp_path)) == [str(tmp_path / "tests"), str(tmp_path / "extra")]


@pytest.mark.unit
def test_a_testpaths_that_is_neither_a_string_nor_a_list_declares_no_roots(tmp_path):
    _dirs(tmp_path, "tests")
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\ntestpaths = 5\n")

    assert configured_testpaths(str(tmp_path)) == []


@pytest.mark.unit
def test_a_pytest_ini_wins_over_a_pyproject_testpaths(tmp_path):
    _dirs(tmp_path, "tests", "other")
    (tmp_path / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n")
    (tmp_path / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths = ["other"]\n')

    assert configured_testpaths(str(tmp_path)) == [str(tmp_path / "tests")]


@pytest.mark.unit
def test_an_empty_pytest_ini_wins_over_a_pyproject_testpaths(tmp_path):
    _dirs(tmp_path, "tests")
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')

    assert configured_testpaths(str(tmp_path)) == []


@pytest.mark.unit
def test_a_pyproject_without_an_ini_options_table_falls_through_to_tox_ini(tmp_path):
    _dirs(tmp_path, "tests")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    (tmp_path / "tox.ini").write_text("[pytest]\ntestpaths = tests\n")

    assert configured_testpaths(str(tmp_path)) == [str(tmp_path / "tests")]


@pytest.mark.unit
def test_a_setup_cfg_tool_pytest_section_is_read_last(tmp_path):
    _dirs(tmp_path, "tests")
    (tmp_path / "setup.cfg").write_text("[tool:pytest]\ntestpaths = tests\n")

    assert configured_testpaths(str(tmp_path)) == [str(tmp_path / "tests")]


@pytest.mark.unit
def test_a_glob_expands_to_every_matching_directory_in_sorted_order(tmp_path):
    _dirs(tmp_path, "tests/b", "tests/a")
    (tmp_path / "pytest.ini").write_text("[pytest]\ntestpaths = tests/*\n")

    assert configured_testpaths(str(tmp_path)) == [str(tmp_path / "tests" / "a"), str(tmp_path / "tests" / "b")]


@pytest.mark.unit
def test_a_pattern_that_matches_nothing_yields_no_root(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\ntestpaths = missing\n")

    assert configured_testpaths(str(tmp_path)) == []


@pytest.mark.unit
def test_a_directory_with_no_pytest_configuration_declares_no_roots(tmp_path):
    assert configured_testpaths(str(tmp_path)) == []


@pytest.mark.unit
def test_a_malformed_pyproject_declares_no_roots_and_does_not_fall_through(tmp_path):
    _dirs(tmp_path, "tests")
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options\n")
    (tmp_path / "tox.ini").write_text("[pytest]\ntestpaths = tests\n")

    assert configured_testpaths(str(tmp_path)) == []


@pytest.mark.unit
def test_a_double_star_testpaths_glob_reaches_a_directory_nested_two_levels_down(tmp_path):
    _dirs(tmp_path, "pkg/a/b/tests")
    (tmp_path / "pytest.ini").write_text("[pytest]\ntestpaths = pkg/**/tests\n")

    assert configured_testpaths(str(tmp_path)) == [str(tmp_path / "pkg" / "a" / "b" / "tests")]
