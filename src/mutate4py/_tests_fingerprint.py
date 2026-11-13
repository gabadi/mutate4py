"""Pytest-run fingerprint and the no-change skip predicate (design 89 §5b).

`tests_fingerprint` hashes every input a Measurement and every tests-digest can
read: the Python files under the collection roots, the conftests above them,
the pytest configuration, the lockfile, the --pytest-args string, the Python
version and the mutate4py version. Equal fingerprints therefore prove the
digests would come out the same.

`can_skip_measurement` decides from per-target facts the caller reduced from
the stored Manifests. This module reads no Manifest itself. Its only import is
`primitives` (`_py_tree`), which `domain` reaches for free, so it stays in
`domain` with `depends_on = []`.
"""

import configparser
import dataclasses
import glob
import hashlib
import importlib.metadata
import json
import os
import re
import shlex
import sys
import tomllib
import uuid
from collections.abc import Sequence

from mutate4py._py_tree import walkable_dirs


@dataclasses.dataclass(frozen=True)
class TargetFacts:
    """What one target's stored Manifest and source say about a skip.

    `manifest_fingerprint` is the `tests_fingerprint` the Manifest records, or
    None when there is no Manifest or it carries no fingerprint. The other
    flags are the caller's reading of the source and the scores.
    """

    manifest_fingerprint: str | None
    source_unchanged: bool
    fully_scored: bool
    accepted_markers_intact: bool


def _target_skippable(facts: TargetFacts, fresh_fingerprint: str) -> bool:
    return (
        facts.manifest_fingerprint == fresh_fingerprint
        and facts.source_unchanged
        and facts.fully_scored
        and facts.accepted_markers_intact
    )


def can_skip_measurement(
    targets: Sequence[TargetFacts],
    fresh_fingerprint: str,
    *,
    mutate_all: bool,
) -> bool:
    """True when the run may skip the Measurement and every Mutant (spec §5b).

    `mutate_all` is keyword-only because it is a bare boolean. A run with no
    targets never skips: there is nothing to report from stored scores.
    """
    if mutate_all or not targets:
        return False
    return all(_target_skippable(facts, fresh_fingerprint) for facts in targets)


def _file_sha(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _py_inputs(root: str, base: str) -> list[tuple[str, str]]:
    """(base-relative path, content sha) for every *.py under `root`."""
    found: list[tuple[str, str]] = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = walkable_dirs(dirs)
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(dirpath, name)
                found.append((os.path.relpath(path, base), _file_sha(path)))
    return found


def _file_input(path: str, base: str) -> tuple[str, str]:
    """One named file's (base-relative path, content sha).

    A missing file records "absent", so creating it later changes the key.
    """
    return os.path.relpath(path, base), (_file_sha(path) if os.path.isfile(path) else "absent")


def _root_inputs(root: str, base: str) -> list[tuple[str, str]]:
    """Inputs under one collection root: every *.py beneath a directory, or the one named file."""
    if os.path.isdir(root):
        return _py_inputs(root, base)
    return [_file_input(root, base)]


def _ancestors(path: str) -> list[str]:
    """`path` and every directory above it, up to the filesystem root."""
    found: list[str] = []
    current = os.path.abspath(path)
    while True:
        found.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            return found
        current = parent


def _conftest_inputs(root: str, base: str) -> list[tuple[str, str]]:
    """conftest.py in every directory above `root`, since pytest loads each one it finds."""
    directories = _ancestors(os.path.dirname(os.path.abspath(root)))
    return [_file_input(os.path.join(directory, "conftest.py"), base) for directory in directories]


# A flag that takes no separate value: a bare switch, a value attached with `=`, or a value attached directly.
# Any other flag may consume the next token, so reading that token as a path would be wrong.
_VALUELESS_FLAG = re.compile(r"-[vqsxl]+|--(lf|ff|pdb|trace|strict-markers|no-header)|--[\w-]+=.+|-[a-zA-Z].+")


def _attached_value(token: str, name: str) -> str | None:
    """The value `token` carries for option `name`: `--name=value`, or `-Nvalue` for a one-letter option."""
    if name.startswith("--"):
        return token[len(name) + 1 :] if token.startswith(name + "=") else None
    return token[len(name) :] if token.startswith(name) and len(token) > len(name) else None


def _option_values(tokens: list[str], name: str) -> list[str]:
    """Every value given to option `name`, as `name value`, `name=value`, or attached to a short name."""
    values: list[str] = []
    for index, token in enumerate(tokens):
        attached = _attached_value(token, name)
        if attached is not None:
            values.append(attached)
        elif token == name and index + 1 < len(tokens):
            values.append(tokens[index + 1])
    return values


def _positional_roots(cwd: str, tokens: list[str]) -> list[str]:
    """Pytest's positional arguments, resolved against `cwd`; nodeid suffixes (`::name`) are dropped."""
    return [os.path.join(cwd, token.split("::")[0]) for token in tokens if not token.startswith("-")]


def _configured_testpaths(cwd: str) -> list[str]:
    """`testpaths` from pytest.ini, each glob expanded as pytest expands it.

    A file that does not parse, and a glob that matches nothing, yield no root
    for that entry. When no entry matches, the walk widens to `cwd`, as pytest does.
    """
    parser = configparser.ConfigParser()
    try:
        parser.read(os.path.join(cwd, "pytest.ini"))
        testpaths = parser.get("pytest", "testpaths", fallback="")
    except configparser.Error:
        return []
    found: list[str] = []
    for pattern in testpaths.split():
        found.extend(sorted(glob.glob(os.path.join(cwd, pattern), recursive=True)))
    return found


def _collection_roots(cwd: str, tokens: list[str]) -> list[str]:
    """Positional arguments, else configured testpaths, else the rootdir (here `cwd`).

    A flag this reader cannot classify may take the next token as its value, so the
    positional reading would be wrong. The walk then widens to the whole rootdir.
    """
    if not all(_VALUELESS_FLAG.fullmatch(token) for token in tokens if token.startswith("-")):
        return [cwd]
    return _positional_roots(cwd, tokens) or _configured_testpaths(cwd) or [cwd]


_CONFIG_FILES = ("pytest.ini", "tox.ini", "setup.cfg")


def _pyproject_pytest_table(directory: str) -> str:
    """The `[tool.pytest]` table of a pyproject.toml as canonical JSON.

    A file that does not parse is hashed whole.
    """
    path = os.path.join(directory, "pyproject.toml")
    if not os.path.isfile(path):
        return "absent"
    try:
        with open(path, "rb") as handle:
            table = tomllib.load(handle).get("tool", {}).get("pytest")
    except (tomllib.TOMLDecodeError, AttributeError):
        return f"unparseable:{_file_sha(path)}"
    return json.dumps(table, sort_keys=True, default=str)


def _config_inputs(directory: str, base: str) -> list[tuple[str, str]]:
    """Every config file pytest may read from `directory`, plus its pytest table.

    Hashing every candidate only over-invalidates, which is the safe direction.
    """
    found = [_file_input(os.path.join(directory, name), base) for name in _CONFIG_FILES]
    pyproject = os.path.relpath(os.path.join(directory, "pyproject.toml"), base)
    found.append((pyproject, _pyproject_pytest_table(directory)))
    return found


def _explicit_config_inputs(cwd: str, tokens: list[str]) -> list[tuple[str, str]]:
    """The file named by each `-c`, hashed whole, wherever it lives."""
    found: list[tuple[str, str]] = []
    for value in _option_values(tokens, "-c"):
        key, sha = _file_input(os.path.join(cwd, value), cwd)
        found.append((f"<-c {key}>", sha))
    return found


def _config_dirs(cwd: str, roots: list[str], tokens: list[str]) -> list[str]:
    """Each start point and every directory above it. Start points: the run directory, each root, each --rootdir."""
    rootdirs = [os.path.join(cwd, value) for value in _option_values(tokens, "--rootdir")]
    starts = [cwd, *roots, *rootdirs]
    return list(dict.fromkeys(directory for start in starts for directory in _ancestors(start)))


def _config_and_lock_inputs(cwd: str, roots: list[str], tokens: list[str]) -> list[tuple[str, str]]:
    found = [_file_input(os.path.join(cwd, "uv.lock"), cwd), *_explicit_config_inputs(cwd, tokens)]
    for directory in _config_dirs(cwd, roots, tokens):
        found.extend(_config_inputs(directory, cwd))
    return found


def _mutate4py_version() -> str:
    try:
        return importlib.metadata.version("mutate4py")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _digest(cwd: str, pytest_args: str) -> str:
    tokens = shlex.split(pytest_args)
    roots = _collection_roots(cwd, tokens)
    entries: dict[str, str] = {}
    for root in roots:
        entries.update(_root_inputs(root, cwd))
        entries.update(_conftest_inputs(root, cwd))
    entries.update(_config_and_lock_inputs(cwd, roots, tokens))
    entries["<pytest-args>"] = pytest_args
    entries["<python-version>"] = sys.version
    entries["<mutate4py-version>"] = _mutate4py_version()
    return hashlib.sha256(json.dumps(sorted(entries.items())).encode()).hexdigest()


def tests_fingerprint(cwd: str, pytest_args: str) -> str:
    """SHA-256 over the run's test inputs (spec §5b). Equal fingerprints mean equal digests.

    An input that cannot be read (unbalanced quotes, an undecodable file) yields a fresh
    value, so it never matches an earlier run and the caller measures instead of skipping.
    """
    try:
        return _digest(cwd, pytest_args)
    except (ValueError, OSError):
        return f"unreadable:{uuid.uuid4().hex}"
