"""Where pytest finds its inifile, read the way pytest reads it, and the options that override the search.

`_tests_fingerprint` stops its ancestor walks at the directory holding the inifile, since pytest
loads neither configuration nor conftests above it. This module is stdlib-only, so it sits in
`primitives` (see tach.toml), and is split from `_tests_fingerprint` for its size cap.
"""

import configparser
import os
import tomllib

__all__ = [
    "CONFIG_FILES",
    "ancestors",
    "conftest_bounds",
    "explicit_bound",
    "inifile_dir",
    "last_option_value",
    "option_values",
    "up_to",
]


def ancestors(path: str) -> list[str]:
    """`path` and every directory above it, up to the filesystem root.

    Pytest's rootdir and conftest search walks that far, so the inputs it loads can sit anywhere above.
    """
    found: list[str] = []
    current = os.path.abspath(path)
    while True:
        found.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            return found
        current = parent


# The config files pytest may read, apart from pyproject.toml (which `_pyproject_configures_pytest` reads).
CONFIG_FILES = ("pytest.ini", ".pytest.ini", "pytest.toml", ".pytest.toml", "tox.ini", "setup.cfg")


def _has_ini_section(path: str, section: str) -> bool:
    """Whether the ini file at `path` has `[section]`. A file that does not parse has none."""
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except (configparser.Error, UnicodeDecodeError):
        return False
    return parser.has_section(section)


def _pyproject_configures_pytest(path: str) -> bool:
    """Whether pyproject.toml carries pytest configuration: `[tool.pytest.ini_options]`, or `[tool.pytest]` keys.

    findpaths.py:122-153: `tool.pytest` keys other than `ini_options` are the TOML-mode config
    (:125, :137), and an `ini_options` table is the ini-mode config (:127, :144). An empty
    `[tool.pytest]` is neither, so the file is not an inifile. One that does not parse is not either.
    """
    try:
        with open(path, "rb") as handle:
            table = tomllib.load(handle).get("tool", {}).get("pytest", {})
    except (tomllib.TOMLDecodeError, AttributeError, UnicodeDecodeError):
        return False
    return isinstance(table, dict) and (any(key != "ini_options" for key in table) or "ini_options" in table)


def _is_inifile(path: str) -> bool:
    """Whether pytest accepts the existing file `path` as its inifile.

    `load_config_dict_from_file`, findpaths.py:58-155:

    - pytest.ini and .pytest.ini always are, even empty (:66, :76-77).
    - pytest.toml and .pytest.toml always are, even empty (:108-118).
    - pyproject.toml is when it has a pytest table (:120-153), see `_pyproject_configures_pytest`.
    - tox.ini is when it has `[pytest]` (:66-73).
    - setup.cfg is when it has `[tool:pytest]` (:80-87). A bare `[pytest]` there is an error, not an inifile (:88-91).
    """
    name = os.path.basename(path)
    if name in ("pytest.ini", ".pytest.ini", "pytest.toml", ".pytest.toml"):
        return True
    if name == "pyproject.toml":
        return _pyproject_configures_pytest(path)
    if name == "tox.ini":
        return _has_ini_section(path, "pytest")
    return name == "setup.cfg" and _has_ini_section(path, "tool:pytest")


def _holds_inifile(directory: str) -> bool:
    """Whether `directory` holds a file pytest accepts as its inifile."""
    paths = [os.path.join(directory, name) for name in (*CONFIG_FILES, "pyproject.toml")]
    return any(os.path.isfile(path) and _is_inifile(path) for path in paths)


def inifile_dir(start: str) -> str | None:
    """The directory of the inifile pytest finds searching up from `start`, or None when there is none.

    `locate_config` (findpaths.py:158-202) checks each directory from `start` up to `/`, and the first
    holding an accepted inifile wins (:181-199). Failing that, the first pyproject.toml met on the way is
    taken as the inifile, with no configuration (:187-188, :200-201).
    """
    directories = ancestors(start)
    held = next((directory for directory in directories if _holds_inifile(directory)), None)
    return held or next((d for d in directories if os.path.isfile(os.path.join(d, "pyproject.toml"))), None)


def up_to(directories: list[str], bound: str | None) -> list[str]:
    """`directories` (nearest first) cut after `bound`, inclusive; whole when `bound` is not among them or is None."""
    return directories[: directories.index(bound) + 1] if bound in directories else directories


def _attached_value(token: str, name: str) -> str | None:
    """The value `token` carries for option `name`: `--name=value`, or `-Nvalue` for a one-letter option."""
    if name.startswith("--"):
        return token[len(name) + 1 :] if token.startswith(name + "=") else None
    return token[len(name) :] if token.startswith(name) and len(token) > len(name) else None


def option_values(tokens: list[str], name: str) -> list[str]:
    """Every value given to option `name`, as `name value`, `name=value`, or attached to a short name."""
    values: list[str] = []
    for index, token in enumerate(tokens):
        attached = _attached_value(token, name)
        if attached is not None:
            values.append(attached)
        elif token == name and index + 1 < len(tokens):
            values.append(tokens[index + 1])
    return values


def last_option_value(tokens: list[str], name: str) -> str | None:
    """The value of the last `name` option: argparse keeps the last one given."""
    values = option_values(tokens, name)
    return values[-1] if values else None


def explicit_bound(cwd: str, tokens: list[str]) -> list[str] | None:
    """The bound an explicit option sets: `--confcutdir`, else the directory of the `-c` file (findpaths.py:307-311)."""
    confcutdir = last_option_value(tokens, "--confcutdir")
    inifile = last_option_value(tokens, "-c")
    if confcutdir:
        return [os.path.abspath(os.path.join(cwd, confcutdir))]
    return [os.path.dirname(os.path.abspath(os.path.join(cwd, inifile)))] if inifile else None


def _rootdir_option(cwd: str, tokens: list[str]) -> str | None:
    """The `--rootdir` directory, absolute, or None."""
    value = last_option_value(tokens, "--rootdir")
    return os.path.abspath(os.path.join(cwd, os.path.expandvars(value))) if value else None


def conftest_bounds(cwd: str, tokens: list[str], starts: list[str]) -> list[str] | None:
    """The directories where conftest loading ends, or None when it reaches the filesystem root.

    pytest loads a conftest from every directory that is not strictly above `confcutdir`
    (config/__init__.py:669-682, :703-704). Its default is the inifile's directory, else the rootdir
    (config/__init__.py:1598-1603). So, in order:
    - `--confcutdir`, then the directory of the `-c` file;
    - the inifile's directory, for each of `starts` (where pytest's search may begin);
    - with no inifile, `--rootdir`;
    - with neither, no bound: the walk goes to `/`.

    Left out: `--noconftest`, `-p` plugins and `conftest.py` files found by `--pyargs`.
    """
    explicit = explicit_bound(cwd, tokens)
    if explicit:
        return explicit
    fallback = _rootdir_option(cwd, tokens)
    bounds = list(dict.fromkeys(inifile_dir(start) or fallback for start in starts))
    return None if None in bounds else list(filter(None, bounds))
