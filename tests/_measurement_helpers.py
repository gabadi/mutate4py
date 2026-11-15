"""Builders for an in-memory Measurement, so run-level tests can state the
coverage a session would have recorded without running pytest.

`measurement_for` indexes CoverageData built with `no_disk=True` through the
same `measurement_from` the real session uses, so a test that injects one
exercises the gate and the report exactly as a measured run does.
"""

import os

from coverage import CoverageData

from mutate4py._measure_record import MeasureRecord
from mutate4py._measurement import Measurement, measurement_from

__all__ = ["measurement_for", "record_for"]


def record_for(**overrides) -> MeasureRecord:
    fields = {
        "core": "ctrace",
        "collected": 1,
        "args": ("tests",),
        "rootdir": "/proj",
        "inipath": None,
        "tests": {},
        "requested": {},
        "fixture_setups": (),
        "failed": (),
        "test_files": (),
        "conftests": (),
        "support_modules": (),
    }
    fields.update(overrides)
    return MeasureRecord(**fields)


def _record_naming_its_test_files(path: str, lines_by_context: dict[str, list[int]], collected: int) -> MeasureRecord:
    """The record a session would hold for these contexts: rootdir is the source's directory (the
    project root in these tests), and each node id's test file is listed as collected. The digest
    reads every listed file, so each one must exist on disk."""
    rootdir = os.path.dirname(path)
    test_files = sorted({os.path.join(rootdir, context.split("::")[0]) for context in lines_by_context if context})
    return record_for(collected=collected, rootdir=rootdir, test_files=tuple(test_files))


def measurement_for(
    path: str,
    lines_by_context: dict[str, list[int]],
    *,
    wall: float = 1.0,
    collected: int = 1,
    record: MeasureRecord | None = None,
) -> Measurement:
    """A Measurement in which `path`'s lines were reached under each context.

    The Empty context is spelled "" (import-time lines); any other key is a
    test node id, whose test file the default record lists as collected.
    `record` replaces the default record when a test needs the session's
    conftests, support modules or a rootdir of its own."""
    data = CoverageData(no_disk=True)
    try:
        for context, lines in lines_by_context.items():
            data.set_context(context)
            data.add_lines({path: lines})
        default = _record_naming_its_test_files(path, lines_by_context, collected)
        return measurement_from(data, record or default, wall=wall)
    finally:
        data.close(force=True)
