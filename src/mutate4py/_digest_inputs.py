"""Build the plain DigestInputs a function digest reads, from one session's record.

The record holds absolute paths and the reach comes from the Measurement's
contexts. Everything here is re-expressed relative to rootdir, the form
`_tests_digest` hashes. Acceptance helpers and other files outside every test
root never reach this module: the plugin's `_support_modules` filters them.
"""

import os
from collections.abc import Iterable, Mapping
from pathlib import Path

from mutate4py._measure_record import MeasureRecord
from mutate4py._sidecar_io import SIDECAR_SUFFIX
from mutate4py._tests_digest import DigestInputs

__all__ = ["digest_inputs_from"]

_LOCKFILE = "uv.lock"
_TEST_FOLDER_NAMES = frozenset({"tests", "test"})


def digest_inputs_from(record: MeasureRecord, reach: Mapping[str, Mapping[int, frozenset[str]]]) -> DigestInputs:
    rootdir = os.path.realpath(record.rootdir)
    conftests_for = _conftests_for(record, rootdir)
    return DigestInputs(
        rootdir=Path(rootdir),
        reach=reach,
        all_test_files=frozenset(conftests_for),
        conftests_for=conftests_for,
        support_files=frozenset(_support_files(record, rootdir)),
    )


def _conftests_for(record: MeasureRecord, rootdir: str) -> dict[str, tuple[str, ...]]:
    absolute_conftests = [os.path.realpath(path) for path in record.conftests]
    return {
        _relative(test_file, rootdir): tuple(
            _relative(conftest, rootdir) for conftest in _chain(os.path.realpath(test_file), absolute_conftests)
        )
        for test_file in record.test_files
    }


def _support_files(record: MeasureRecord, rootdir: str) -> set[str]:
    support = {_relative(path, rootdir) for path in record.support_modules}
    if record.inipath is not None:
        support.add(_relative(record.inipath, rootdir))
    if os.path.isfile(os.path.join(rootdir, _LOCKFILE)):
        support.add(_LOCKFILE)
    return support | _data_files(record, rootdir)


def _data_files(record: MeasureRecord, rootdir: str) -> set[str]:
    return {_relative(path, rootdir) for root in _test_folders(record, rootdir) for path in _data_paths(root)}


def _test_folders(record: MeasureRecord, rootdir: str) -> set[str]:
    return {
        folder
        for test_file in record.test_files
        if (folder := _test_folder(os.path.realpath(test_file), rootdir)) is not None
    }


def _test_folder(test_file: str, rootdir: str) -> str | None:
    directory = os.path.dirname(test_file)
    named = None
    candidate = directory
    while candidate.startswith(rootdir + os.sep):
        if os.path.basename(candidate) in _TEST_FOLDER_NAMES:
            named = candidate
        candidate = os.path.dirname(candidate)
    if named is not None:
        return named
    return directory if directory.startswith(rootdir + os.sep) else None


def _data_paths(root: str) -> list[str]:
    return [
        os.path.join(directory, name)
        for directory, names in _walk_visible(root)
        for name in names
        if _is_data_name(name)
    ]


def _is_data_name(name: str) -> bool:
    return not (name.endswith(".py") or name.endswith(SIDECAR_SUFFIX) or name.startswith("."))


def _walk_visible(root: str) -> Iterable[tuple[str, list[str]]]:
    for directory, subdirectories, names in os.walk(root):
        subdirectories[:] = [name for name in subdirectories if name != "__pycache__" and not name.startswith(".")]
        yield directory, names


def _relative(path: str, rootdir: str) -> str:
    return os.path.relpath(os.path.realpath(path), rootdir)


def _chain(test_file: str, conftests: Iterable[str]) -> list[str]:
    """The conftests in the test file's directory or any ancestor, sorted."""
    return sorted(conftest for conftest in conftests if test_file.startswith(os.path.dirname(conftest) + os.sep))
