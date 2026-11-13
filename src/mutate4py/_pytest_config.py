"""Where pytest's configuration declares its `testpaths`, read the way pytest reads them.

`_collection_roots` in `_tests_fingerprint` widens a run's walk to these paths when
the run names no path of its own. pytest takes the first configuration file that
configures it: pytest.ini, then the `[tool.pytest.ini_options]` table of
pyproject.toml, then the `[pytest]` section of tox.ini, then `[tool:pytest]` of
setup.cfg. This module is stdlib-only, so it sits in `primitives` (see tach.toml).
"""

import configparser
import glob
import os
import tomllib


def _ini_testpaths(path: str, section: str) -> list[str] | None:
    """`testpaths` of `section` in an ini file: None when the file names no such section, [] when it does not parse."""
    parser = configparser.ConfigParser()
    try:
        parser.read(path)
        if not parser.has_section(section):
            return None
        return parser.get(section, "testpaths", fallback="").split()
    except configparser.Error:
        return []


def _testpath_patterns(value: object) -> list[str]:
    """A `testpaths` value as pytest reads it: a string is split on whitespace, a list is taken item by item."""
    if isinstance(value, str):
        return value.split()
    return [str(item) for item in value] if isinstance(value, list) else []


def _pyproject_testpaths(cwd: str) -> list[str] | None:
    """`testpaths` of the `[tool.pytest.ini_options]` table of pyproject.toml: None when there is no such table."""
    path = os.path.join(cwd, "pyproject.toml")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as handle:
            table = tomllib.load(handle).get("tool", {}).get("pytest", {}).get("ini_options")
        if table is None:
            return None
        value = table.get("testpaths", [])
    except (tomllib.TOMLDecodeError, AttributeError):
        return []
    return _testpath_patterns(value)


def _declared_testpaths(cwd: str) -> list[str]:
    """The `testpaths` patterns of the configuration file pytest reads from `cwd`.

    pytest takes the first file that configures it: pytest.ini (even when empty),
    then the `[tool.pytest.ini_options]` table of pyproject.toml, then the `[pytest]`
    section of tox.ini, then the `[tool:pytest]` section of setup.cfg. None of them: no patterns.
    """
    pytest_ini = os.path.join(cwd, "pytest.ini")
    if os.path.isfile(pytest_ini):
        return _ini_testpaths(pytest_ini, "pytest") or []
    pyproject = _pyproject_testpaths(cwd)
    if pyproject is not None:
        return pyproject
    tox_ini = _ini_testpaths(os.path.join(cwd, "tox.ini"), "pytest")
    if tox_ini is not None:
        return tox_ini
    return _ini_testpaths(os.path.join(cwd, "setup.cfg"), "tool:pytest") or []


def configured_testpaths(cwd: str) -> list[str]:
    """The configured `testpaths`, each glob expanded as pytest expands it.

    A file that does not parse, and a glob that matches nothing, yield no root
    for that entry. When no entry matches, the walk widens to `cwd`, as pytest does.
    """
    found: list[str] = []
    for pattern in _declared_testpaths(cwd):
        found.extend(sorted(glob.glob(os.path.join(cwd, pattern), recursive=True)))
    return found
