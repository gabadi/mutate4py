"""The record one Measurement session writes, and the pure logic behind it.

`_measure_plugin` runs inside the user's pytest session and must stay thin:
it is boundary code no Mutant run measures. Everything it decides — the core
name, how a test's phases add up, which test a fixture setup is charged to,
which loaded modules are test helpers — lives here instead, where unit tests
reach it. `_measurement` reads the same record back, so the format has exactly
one definition.

No dependencies: the plugin imports this module from inside the session.
"""

import json
import os
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field

__all__ = [
    "FixtureSetup",
    "MeasureRecord",
    "SessionFacts",
    "SessionLog",
    "Timing",
    "core_from_sys_info",
    "dump_record",
    "load_record",
    "file_of_test",
]

_TRACER_CORES = {"CTracer": "ctrace", "PyTracer": "pytrace", "SysMonitor": "sysmon"}
_CONFTEST = "conftest.py"


def core_from_sys_info(sys_info: Iterable[tuple[str, object]]) -> str:
    """The core coverage.py is actually running, from `Coverage.sys_info()`.

    An unknown tracer name is returned as given, so a refusal can name it."""
    tracer = str(dict(sys_info).get("core"))
    return _TRACER_CORES.get(tracer, tracer)


def file_of_test(nodeid: str) -> str:
    """The test file part of a node id, relative to rootdir like the id itself."""
    return nodeid.split("::", 1)[0]


@dataclass(frozen=True)
class Timing:
    """One test's measured time: the whole protocol, and its setup phase alone."""

    duration: float
    setup: float


@dataclass(frozen=True)
class FixtureSetup:
    """One fixture setup pytest actually ran, charged to the file of the test
    that was running when it happened."""

    fixture: str
    scope: str
    duration: float
    test_file: str


@dataclass(frozen=True)
class SessionFacts:
    """What the plugin reads off the finished session, as plain values."""

    core: str
    collected: int
    args: tuple[str, ...]
    rootdir: str
    inipath: str | None
    plugin_files: tuple[str, ...]
    module_files: tuple[str, ...]
    test_files: tuple[str, ...]
    # Files of the items pytest deselected (`-m`, `-k`): test modules too, never helpers.
    deselected_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class MeasureRecord:
    """Everything one Measurement session recorded, besides the coverage data.

    `tests`, `requested` and `fixture_setups` use pytest's node ids and
    rootdir-relative test files; `test_files`, `conftests` and
    `support_modules` are absolute paths."""

    core: str
    collected: int
    args: tuple[str, ...]
    rootdir: str
    inipath: str | None
    tests: dict[str, Timing]
    requested: dict[str, tuple[str, ...]]
    fixture_setups: tuple[FixtureSetup, ...]
    failed: tuple[str, ...]
    test_files: tuple[str, ...]
    conftests: tuple[str, ...]
    support_modules: tuple[str, ...]


def _test_roots(test_files: Iterable[str], rootdir: str) -> set[str]:
    """The directory of each test file and its ancestors, stopping below rootdir."""
    roots = set()
    for test_file in test_files:
        directory = os.path.dirname(test_file)
        while directory.startswith(rootdir + os.sep):
            roots.add(directory)
            directory = os.path.dirname(directory)
    return roots


def _support_modules(facts: SessionFacts, conftests: tuple[str, ...]) -> tuple[str, ...]:
    roots = _test_roots(facts.test_files, facts.rootdir)
    excluded = set(facts.test_files) | set(facts.deselected_files) | set(conftests)
    return tuple(
        sorted(
            path for path in set(facts.module_files) - excluded if any(path.startswith(root + os.sep) for root in roots)
        )
    )


@dataclass
class SessionLog:
    """Accumulates the session's events; `finish` turns them into a record."""

    _phases: dict[str, dict[str, float]] = field(default_factory=dict)
    _requested: dict[str, tuple[str, ...]] = field(default_factory=dict)
    _fixture_setups: list[FixtureSetup] = field(default_factory=list)
    _failed: list[str] = field(default_factory=list)
    _current: str = ""

    def test_started(self, nodeid: str, fixturenames: Iterable[str]) -> None:
        self._current = nodeid
        self._phases.setdefault(nodeid, {})
        self._requested[nodeid] = tuple(fixturenames)

    def test_phase(self, nodeid: str, when: str, duration: float, *, failed: bool) -> None:
        self._phases.setdefault(nodeid, {})[when] = duration
        if failed:
            self._fail(nodeid)

    def collection_failed(self, nodeid: str) -> None:
        self._fail(nodeid)

    def fixture_set_up(self, fixture: str, scope: str, duration: float) -> None:
        self._fixture_setups.append(FixtureSetup(fixture, scope, duration, file_of_test(self._current)))

    def _fail(self, nodeid: str) -> None:
        if nodeid not in self._failed:
            self._failed.append(nodeid)

    def finish(self, facts: SessionFacts) -> MeasureRecord:
        tests = {
            nodeid: Timing(duration=sum(phases.values()), setup=phases.get("setup", 0.0))
            for nodeid, phases in self._phases.items()
        }
        conftests = tuple(path for path in facts.plugin_files if os.path.basename(path) == _CONFTEST)
        return MeasureRecord(
            core=facts.core,
            collected=facts.collected,
            args=facts.args,
            rootdir=facts.rootdir,
            inipath=facts.inipath,
            tests=tests,
            requested=dict(self._requested),
            fixture_setups=tuple(self._fixture_setups),
            failed=tuple(self._failed),
            test_files=facts.test_files,
            conftests=conftests,
            support_modules=_support_modules(facts, conftests),
        )


def dump_record(record: MeasureRecord) -> str:
    return json.dumps(asdict(record))


def load_record(text: str) -> MeasureRecord:
    raw = json.loads(text)
    return MeasureRecord(
        core=raw["core"],
        collected=raw["collected"],
        args=tuple(raw["args"]),
        rootdir=raw["rootdir"],
        inipath=raw["inipath"],
        tests={nodeid: Timing(**timing) for nodeid, timing in raw["tests"].items()},
        requested={nodeid: tuple(names) for nodeid, names in raw["requested"].items()},
        fixture_setups=tuple(FixtureSetup(**setup) for setup in raw["fixture_setups"]),
        failed=tuple(raw["failed"]),
        test_files=tuple(raw["test_files"]),
        conftests=tuple(raw["conftests"]),
        support_modules=tuple(raw["support_modules"]),
    )
