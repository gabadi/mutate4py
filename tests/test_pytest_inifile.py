"""Unit tests for _pytest_inifile.py: a `--confcutdir` pytest takes from addopts leaves the conftest walk unbounded."""

import pytest

from mutate4py._pytest_inifile import conftest_bounds

_FILES = {
    "pytest.ini": "[pytest]\naddopts = -q {opts}\n",
    ".pytest.ini": "[pytest]\naddopts = -q {opts}\n",
    "tox.ini": "[pytest]\naddopts = -q {opts}\n",
    "setup.cfg": "[tool:pytest]\naddopts = -q {opts}\n",
    "pyproject.toml": "[tool.pytest.ini_options]\naddopts = '-q {opts}'\n",
    "pyproject-list": "[tool.pytest.ini_options]\naddopts = ['-q', '{opts}']\n",
    "pyproject-toml-mode": "[tool.pytest]\naddopts = ['-q', '{opts}']\n",
    "pytest.toml": "[pytest]\naddopts = ['-q', '{opts}']\n",
    ".pytest.toml": "[pytest]\naddopts = '-q {opts}'\n",
}


def _write(directory, key: str, opts: str) -> None:
    name = "pyproject.toml" if key.startswith("pyproject") else key
    (directory / name).write_text(_FILES[key].format(opts=opts))


@pytest.fixture(autouse=True)
def _no_ambient_addopts(monkeypatch):
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)


@pytest.mark.unit
@pytest.mark.parametrize("key", list(_FILES))
def test_an_inifile_addopts_without_confcutdir_keeps_the_inifile_bound(tmp_path, key):
    _write(tmp_path, key, "--tb=short")
    assert conftest_bounds(str(tmp_path), [], [str(tmp_path)]) == [str(tmp_path)]


@pytest.mark.unit
@pytest.mark.parametrize("key", list(_FILES))
@pytest.mark.parametrize("spelling", ["--confcutdir=.", "--confcutdir ."])
def test_confcutdir_in_the_inifile_addopts_leaves_no_bound(tmp_path, key, spelling):
    _write(tmp_path, key, spelling)
    assert conftest_bounds(str(tmp_path), [], [str(tmp_path)]) is None


@pytest.mark.unit
def test_confcutdir_in_the_addopts_of_a_parent_inifile_leaves_no_bound(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = --confcutdir=.\n")
    run = tmp_path / "sub"
    run.mkdir()
    assert conftest_bounds(str(run), [], [str(run)]) is None


@pytest.mark.unit
def test_confcutdir_in_the_addopts_of_another_start_point_leaves_no_bound(tmp_path):
    inside = tmp_path / "inside"
    inside.mkdir()
    (inside / "pytest.ini").write_text("[pytest]\naddopts = --confcutdir=.\n")
    other = tmp_path / "other"
    other.mkdir()
    (other / "pytest.ini").write_text("[pytest]\n")
    assert conftest_bounds(str(other), [], [str(other), str(inside)]) is None


@pytest.mark.unit
def test_confcutdir_in_the_addopts_of_the_config_file_option_leaves_no_bound(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "custom.ini").write_text("[pytest]\naddopts = --confcutdir=.\n")
    assert conftest_bounds(str(tmp_path), ["-c", "custom.ini"], [str(tmp_path)]) is None
    assert conftest_bounds(str(tmp_path), ["--config-file=custom.ini"], [str(tmp_path)]) is None


@pytest.mark.unit
def test_the_config_file_option_hides_the_searched_inifiles_addopts(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = --confcutdir=.\n")
    (tmp_path / "custom.ini").write_text("[pytest]\n")
    assert conftest_bounds(str(tmp_path), ["-c", "custom.ini"], [str(tmp_path)]) == [str(tmp_path)]


@pytest.mark.unit
def test_a_command_line_confcutdir_does_not_override_the_addopts_rule(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = --confcutdir=.\n")
    assert conftest_bounds(str(tmp_path), ["--confcutdir", str(tmp_path)], [str(tmp_path)]) is None


@pytest.mark.unit
def test_a_command_line_confcutdir_alone_still_bounds_the_walk(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = -q\n")
    assert conftest_bounds(str(tmp_path), ["--confcutdir", str(tmp_path)], [str(tmp_path)]) == [str(tmp_path)]


@pytest.mark.unit
def test_confcutdir_in_pytest_addopts_leaves_no_bound(tmp_path, monkeypatch):
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    monkeypatch.setenv("PYTEST_ADDOPTS", "-q --confcutdir=.")
    assert conftest_bounds(str(tmp_path), [], [str(tmp_path)]) is None


@pytest.mark.unit
def test_pytest_addopts_without_confcutdir_keeps_the_bound(tmp_path, monkeypatch):
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    monkeypatch.setenv("PYTEST_ADDOPTS", "-q --tb=short")
    assert conftest_bounds(str(tmp_path), [], [str(tmp_path)]) == [str(tmp_path)]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "content"),
    [
        pytest.param("pyproject.toml", "[tool.pytest.ini_options\n", id="unparseable-toml"),
        pytest.param("pyproject.toml", "[tool.pytest]\nini_options = 5\naddopts = 7\n", id="non-string-addopts"),
        pytest.param("pytest.toml", "pytest = 5\n", id="pytest-is-not-a-table"),
        pytest.param("pyproject.toml", "tool = 5\n", id="tool-is-not-a-table"),
        pytest.param("pytest.ini", "[pytest\n", id="unparseable-ini"),
        pytest.param("pytest.ini", "[pytest]\n", id="no-addopts"),
    ],
)
def test_an_inifile_addopts_that_cannot_be_read_leave_the_bound(tmp_path, name, content):
    (tmp_path / name).write_text(content)
    assert conftest_bounds(str(tmp_path), [], [str(tmp_path)]) == [str(tmp_path)]
