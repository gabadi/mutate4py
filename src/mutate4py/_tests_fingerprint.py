"""Pytest-run fingerprint and the no-change skip predicate (design 89 §5b).

`tests_fingerprint` hashes every input a Measurement and every tests-digest can
read: the Python files under the collection roots, the conftests above them and
the pytest configuration above them (both up to the directory holding pytest's
inifile, else up to the filesystem root, recording only the files that exist),
the lockfile, the --pytest-args string, the Python
version and the mutate4py version. Equal fingerprints therefore prove the
digests would come out the same.

A Python file is hashed with its Manifest footer stripped, so the footer a scored
run writes into a source file never changes the fingerprint that run wrote.

`can_skip_measurement` decides from per-target facts the caller reduced from
the stored Manifests. This module reads no Manifest itself: its one Manifest
import is `strip_manifest`, which removes the footer text and reads no stored
value. Its other imports are `primitives` (`_py_tree`, `_pytest_argv`, `_pytest_config`).
"""

import dataclasses
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

from mutate4py._manifest import strip_manifest
from mutate4py._py_tree import walkable_dirs
from mutate4py._pytest_config import configured_testpaths
from mutate4py._pytest_inifile import (
    CONFIG_FILE_OPTIONS,
    CONFIG_FILES,
    ancestors,
    conftest_bounds,
    inifile_dir,
    option_values,
    up_to,
)
from mutate4py._pytest_argv import VALUE_OPTIONS, flag_tokens, positional_tokens


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


def can_skip_measurement(targets: Sequence[TargetFacts], fresh_fingerprint: str) -> bool:
    """True when the run may skip the Measurement and every Mutant (spec §5b).

    A run with no targets never skips: there is nothing to report from stored scores.
    """
    if not targets:
        return False
    return all(_target_skippable(facts, fresh_fingerprint) for facts in targets)


def _hashable(path: str, content: bytes) -> bytes:
    """What a file's digest reads: a Python file's body with its footer stripped, any other file whole.

    Decoding keeps every byte (surrogateescape), so a non-UTF-8 file still hashes, and an
    undecodable one is never a false match.
    """
    if not path.endswith(".py"):
        return content
    return strip_manifest(content.decode("utf-8", errors="surrogateescape")).encode("utf-8", errors="surrogateescape")


def _file_sha(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(_hashable(path, handle.read())).hexdigest()


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


def _existing_file_input(path: str, base: str) -> list[tuple[str, str]]:
    """The file's (base-relative path, content sha), or nothing when it does not exist.

    An absent file carries no information: creating it adds an entry and deleting it removes
    one, so both changes still move the key, and a checkout with nothing above it has no
    depth-dependent keys.
    """
    return [(os.path.relpath(path, base), _file_sha(path))] if os.path.isfile(path) else []


# A flag that carries everything it needs: a bare switch, a value attached with `=`, or a value attached directly.
# A flag outside this set and outside VALUE_OPTIONS may consume the next token, so the walk widens instead.
_SELF_CONTAINED_FLAG = re.compile(r"-[vqsxl]+|--(lf|ff|pdb|trace|strict-markers|no-header)|--[\w-]+=.+|-[a-zA-Z].+")


def _positional_roots(cwd: str, tokens: list[str]) -> list[str]:
    """Pytest's positional arguments, resolved against `cwd`; nodeid suffixes (`::name`) are dropped."""
    return [os.path.join(cwd, token.split("::")[0]) for token in positional_tokens(tokens)]


def _is_classified_flag(token: str) -> bool:
    """Whether this reader knows the flag's arity: a value option, or a flag that carries its own value."""
    return token in VALUE_OPTIONS or _SELF_CONTAINED_FLAG.fullmatch(token) is not None


def _collection_roots(cwd: str, tokens: list[str]) -> list[str]:
    """Positional arguments, else configured testpaths, else the rootdir (here `cwd`).

    A flag this reader cannot classify may take the next token as its value, so the
    positional reading would be wrong. The walk then widens to the whole rootdir.
    """
    if not all(_is_classified_flag(token) for token in flag_tokens(tokens)):
        return [cwd]
    return _positional_roots(cwd, tokens) or configured_testpaths(cwd) or [cwd]


def _pyproject_pytest_table(path: str) -> str:
    """The `[tool.pytest]` table of the pyproject.toml at `path` as canonical JSON.

    A file that does not parse is hashed whole.
    """
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
    found: list[tuple[str, str]] = []
    for name in CONFIG_FILES:
        found.extend(_existing_file_input(os.path.join(directory, name), base))
    pyproject = os.path.join(directory, "pyproject.toml")
    if os.path.isfile(pyproject):
        found.append((os.path.relpath(pyproject, base), _pyproject_pytest_table(pyproject)))
    return found


def _explicit_config_inputs(cwd: str, tokens: list[str]) -> list[tuple[str, str]]:
    """The file named by each `-c` or `--config-file`, hashed whole, wherever it lives."""
    found: list[tuple[str, str]] = []
    for value in option_values(tokens, *CONFIG_FILE_OPTIONS):
        key, sha = _file_input(os.path.join(cwd, value), cwd)
        found.append((f"<-c {key}>", sha))
    return found


def _pytest_start(cwd: str, tokens: list[str]) -> str:
    """Where pytest starts its inifile search: the common ancestor of the existing positional paths, else `cwd`.

    `determine_setup` (findpaths.py:313) takes `get_common_ancestor` of the argument directories (:205-228,
    :231-250), which is the invocation directory when no argument names an existing path.
    """
    paths = [path for path in _positional_roots(cwd, tokens) if os.path.exists(path)]
    directories = [path if os.path.isdir(path) else os.path.dirname(path) for path in paths]
    return os.path.commonpath(directories) if directories else cwd


def _config_dirs(cwd: str, roots: list[str], tokens: list[str]) -> list[str]:
    """Each directory pytest may read configuration from: from every start point up to its inifile's directory.

    Start points: the run directory, pytest's own start, each root, each --rootdir. Above the inifile's
    directory pytest reads no configuration. With `-c` or `--config-file`, pytest searches for none (findpaths.py:306-311),
    and the named file is hashed by `_explicit_config_inputs`.
    """
    if option_values(tokens, *CONFIG_FILE_OPTIONS):
        return []
    rootdirs = [os.path.join(cwd, value) for value in option_values(tokens, "--rootdir")]
    starts = [cwd, _pytest_start(cwd, tokens), *roots, *rootdirs]
    chains = (up_to(ancestors(start), inifile_dir(start)) for start in starts)
    return list(dict.fromkeys(directory for chain in chains for directory in chain))


def _conftest_chain(root: str, bounds: list[str] | None) -> list[str]:
    """The directories above `root`, nearest first, whose conftest pytest loads.

    pytest skips a directory only when it is strictly above `confcutdir` (`_is_in_confcutdir`,
    config/__init__.py:682, :703-704). A bound at or below `root` therefore leaves no ancestor, and a
    bound beside the chain skips none. With several bounds, a directory is kept when any keeps it.
    """
    directories = ancestors(os.path.dirname(os.path.abspath(root)))
    if not bounds:
        return directories
    strictly_above = [set(ancestors(bound)[1:]) for bound in bounds]
    return [directory for directory in directories if any(directory not in above for above in strictly_above)]


def _conftest_inputs(root: str, base: str, bounds: list[str] | None) -> list[tuple[str, str]]:
    """Each conftest.py pytest loads for `root`, since it loads each one it finds on the way up."""
    found: list[tuple[str, str]] = []
    for directory in _conftest_chain(root, bounds):
        found.extend(_existing_file_input(os.path.join(directory, "conftest.py"), base))
    return found


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


def fingerprint_inputs(cwd: str, pytest_args: str) -> dict[str, str]:
    """Every input the fingerprint hashes, keyed by its base-relative name, each with its content's sha.

    The keys are the list the fingerprint covers; `_digest` hashes exactly these entries.
    """
    tokens = shlex.split(pytest_args)
    roots = _collection_roots(cwd, tokens)
    bounds = conftest_bounds(cwd, tokens, [cwd, _pytest_start(cwd, tokens)])
    entries: dict[str, str] = {}
    for root in roots:
        entries.update(_root_inputs(root, cwd))
        entries.update(_conftest_inputs(root, cwd, bounds))
    entries.update(_config_and_lock_inputs(cwd, roots, tokens))
    entries["<pytest-args>"] = pytest_args
    entries["<python-version>"] = sys.version
    entries["<mutate4py-version>"] = _mutate4py_version()
    return entries


def _digest(cwd: str, pytest_args: str) -> str:
    return hashlib.sha256(json.dumps(sorted(fingerprint_inputs(cwd, pytest_args).items())).encode()).hexdigest()


def tests_fingerprint(cwd: str, pytest_args: str) -> str:
    """SHA-256 over the run's test inputs (spec §5b). Equal fingerprints mean equal digests.

    An input that cannot be read (unbalanced quotes, an undecodable file) yields a fresh
    value, so it never matches an earlier run and the caller measures instead of skipping.
    """
    try:
        return _digest(cwd, pytest_args)
    except (ValueError, OSError):
        return f"unreadable:{uuid.uuid4().hex}"
