"""The Measurement: one pytest session under coverage.py's ctrace core, with
one context per test.

`measure(MeasureRequest) -> Measurement` is the whole interface. Behind it:
the session subprocess, the bootstrap that starts coverage before pytest is
imported, the forced core and its read-back, pytest-cov neutralising, and the
Test map index. Design: issue #89, section 2.
"""

import contextlib
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from types import MappingProxyType

from coverage import CoverageData

from mutate4py._digest_inputs import digest_inputs_from
from mutate4py._measure_record import FixtureSetup, MeasureRecord, file_of_test, load_record
from mutate4py._plugin_neutralisation import neutralising_args
from mutate4py._tests_digest import DigestInputs

__all__ = [
    "ALL",
    "CoverageCoreRefused",
    "MeasureRequest",
    "Measurement",
    "MeasurementFailed",
    "Narrowed",
    "Static",
    "Uncovered",
    "measure",
    "measure_in_scratch",
    "measurement_from",
    "raise_for_session",
]

# Run with `python -c`, not `-m`: coverage starts before pytest, any conftest
# or plugin, and the `mutate4py` package itself are imported, so a run that
# targets `mutate4py/__init__.py` still sees its import-time lines.
# `config_file=False` keeps the user's coverage config (a `core = sysmon`, a
# dynamic-context setting, an omit) out of the session.
_BOOTSTRAP = """
import json, sys
config = json.load(open(sys.argv[1]))
import coverage
cov = coverage.Coverage(config_file=False, data_file=config["data_file"], include=config["include"], branch=False)
cov.set_option("run:disable_warnings", ["no-data-collected"])
try:
    cov.set_option("run:core", "ctrace")
except Exception:
    pass
cov.start()
try:
    import pytest
    from mutate4py._measure_plugin import MeasurePlugin
    status = pytest.main(sys.argv[2:], plugins=[MeasurePlugin(cov, config["record_file"])])
finally:
    cov.stop()
    cov.save()
sys.exit(int(status))
"""
_NO_TESTS_EXIT = 5
# Inherited settings that would start a second collector in the session, or
# point coverage at the user's config.
_DROPPED_ENV = ("COVERAGE_PROCESS_START", "COVERAGE_RCFILE")
_DROPPED_ENV_PREFIX = "COV_CORE_"

_EMPTY_CONTEXT = ""
_SHARED_SCOPES = frozenset({"session", "package"})
_SYSMON_HINT = (
    "mutate4py forces the ctrace core (COVERAGE_CORE=ctrace, coverage's config file ignored); "
    "check that nothing in the Project environment overrides COVERAGE_CORE or restarts coverage, "
    "and that coverage>=7.10 with its C extension is installed there."
)
_PYTRACE_NOTE = (
    "coverage.py's C tracer is unavailable, so the Measurement ran under the pytrace core: correct, but slower."
)


class _All:
    def __repr__(self) -> str:
        return "ALL"


ALL = _All()
"""`budget_of(ALL)`: the full test set, as a static Mutant or a confirmation runs it."""


@dataclass(frozen=True)
class Narrowed:
    """Named tests reached the line: a Mutant there runs exactly these."""

    node_ids: frozenset[str]


@dataclass(frozen=True)
class Static:
    """Only the Empty context reached the line: a Mutant there runs every test."""


@dataclass(frozen=True)
class Uncovered:
    """Nothing reached the line."""


@dataclass(frozen=True)
class MeasureRequest:
    cwd: str
    pytest_args: tuple[str, ...]
    target_files: tuple[str, ...]
    scratch_dir: str

    def __post_init__(self) -> None:
        # coverage.py measures every file when `include` is empty.
        if not self.target_files:
            raise ValueError("the Measurement needs at least one target file")


class MeasurementFailed(Exception):
    """The Measurement session did not pass, so there is no Baseline."""

    def __init__(self, *, failing_node_ids: tuple[str, ...] = (), no_tests: bool = False, reason: str = "") -> None:
        if no_tests:
            message = "the Measurement collected no tests"
        elif failing_node_ids:
            message = "baseline failed: " + ", ".join(failing_node_ids)
        else:
            message = f"baseline failed: {reason}"
        super().__init__(message)
        self.failing_node_ids = failing_node_ids
        self.no_tests = no_tests
        self.reason = reason


class CoverageCoreRefused(Exception):
    def __init__(self, core: str, hint: str) -> None:
        super().__init__(f"the Measurement ran under coverage.py's {core} core, which loses per-test contexts. {hint}")
        self.core = core
        self.hint = hint


def _canonical(path: str) -> str:
    return os.path.realpath(path)


@dataclass(frozen=True)
class Measurement:
    """One passing Measurement session: the Baseline, the Coverage gate's input
    and the Test map, read from the same data so they never disagree."""

    _contexts: MappingProxyType  # canonical path -> line -> frozenset[context]
    _durations: MappingProxyType  # node id -> seconds
    _largest_setup: MappingProxyType  # test file -> seconds
    _record: MeasureRecord
    wall: float

    @property
    def core(self) -> str:
        return self._record.core

    @property
    def note(self) -> str | None:
        return _PYTRACE_NOTE if self.core == "pytrace" else None

    @property
    def tests(self) -> int:
        return self._record.collected

    @property
    def rootdir(self) -> str:
        return self._record.rootdir

    @property
    def positional_args(self) -> tuple[str, ...]:
        """pytest's parsed positional arguments, which a narrowed run replaces."""
        return self._record.args

    @property
    def per_mutant_overhead(self) -> float:
        return max(0.0, self.wall - sum(self._durations.values()))

    def budget_of(self, node_ids: "frozenset[str] | _All") -> float:
        """The tests' summed durations plus the largest fixture setup seen in their files."""
        ids = self._durations.keys() if node_ids is ALL else node_ids
        longest = max(self._durations.values(), default=0.0)
        total = sum(self._durations.get(node_id, longest) for node_id in ids)
        setup = max((self._largest_setup.get(file_of_test(node_id), 0.0) for node_id in ids), default=0.0)
        return total + setup

    def _line_contexts(self, path: str) -> MappingProxyType:
        return self._contexts.get(_canonical(path), MappingProxyType({}))

    def outcome(self, path: str, line: int) -> Narrowed | Static | Uncovered:
        contexts = self._line_contexts(path).get(line, frozenset())
        named = contexts - {_EMPTY_CONTEXT}
        if named:
            return Narrowed(named)
        return Static() if contexts else Uncovered()

    def tests_for_line(self, path: str, line: int) -> tuple[str, list[str]]:
        """The Selection outcome for a line in the planner's terms: ("narrowed", the
        sorted node ids that reached it), ("static", []) or ("uncovered", [])."""
        found = self.outcome(path, line)
        if isinstance(found, Narrowed):
            return "narrowed", sorted(found.node_ids)
        if isinstance(found, Static):
            return "static", []
        return "uncovered", []

    def covered_lines(self, path: str) -> frozenset[int]:
        return frozenset(self._line_contexts(path))

    def empty_lines(self, path: str) -> frozenset[int]:
        return frozenset(line for line, contexts in self._line_contexts(path).items() if _EMPTY_CONTEXT in contexts)

    def digest_inputs(self) -> DigestInputs:
        """The tests digest's inputs: each measured line's reaching test files, and the session's files.
        The Empty context is not a test, so an import-time line reaches no test file."""
        reach = {
            path: {
                line: frozenset(file_of_test(name) for name in names - {_EMPTY_CONTEXT})
                for line, names in lines.items()
            }
            for path, lines in self._contexts.items()
        }
        return digest_inputs_from(self._record, reach)


def _largest_setup_by_file(record: MeasureRecord) -> dict[str, float]:
    """Per test file, the largest fixture setup its tests can pay: any setup
    charged to the file, and any session- or package-scoped one its tests
    request, wherever pytest first set it up."""
    requested_by_file: dict[str, set[str]] = {}
    for node_id, names in record.requested.items():
        requested_by_file.setdefault(file_of_test(node_id), set()).update(names)
    return {
        test_file: max(
            (setup.duration for setup in record.fixture_setups if _payable(setup, test_file, requested)),
            default=0.0,
        )
        for test_file, requested in requested_by_file.items()
    }


def _payable(setup: FixtureSetup, test_file: str, requested: set[str]) -> bool:
    """Whether a test in `test_file` can pay for this setup."""
    return setup.test_file == test_file or (setup.scope in _SHARED_SCOPES and setup.fixture in requested)


def measurement_from(data: CoverageData, record: MeasureRecord, wall: float) -> Measurement:
    """Index one session's coverage data and record into a Measurement.

    Raises CoverageCoreRefused when the session ran under sysmon."""
    if record.core == "sysmon":
        raise CoverageCoreRefused(record.core, _SYSMON_HINT)
    contexts = {
        _canonical(path): MappingProxyType(
            {line: frozenset(names) for line, names in data.contexts_by_lineno(path).items()}
        )
        for path in data.measured_files()
    }
    return Measurement(
        _contexts=MappingProxyType(contexts),
        _durations=MappingProxyType({node_id: timing.duration for node_id, timing in record.tests.items()}),
        _largest_setup=MappingProxyType(_largest_setup_by_file(record)),
        _record=record,
        wall=wall,
    )


def _session_env() -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in _DROPPED_ENV and not key.startswith(_DROPPED_ENV_PREFIX)
    }
    env["COVERAGE_CORE"] = "ctrace"
    return env


def _read_record(record_file: str) -> MeasureRecord | None:
    try:
        with open(record_file) as f:
            return load_record(f.read())
    except FileNotFoundError:
        return None


def _failure_reason(returncode: int, output: bytes) -> str:
    """pytest's last error line (it prints usage and import errors there), else its last line."""
    lines = output.decode(errors="replace").splitlines()
    errors = [line for line in lines if "error:" in line.lower()]
    last = _last_nonblank(errors or lines)
    return f"{last} (exit code {returncode})" if last else f"exit code {returncode}"


def _last_nonblank(lines: list[str]) -> str:
    return next((line.strip() for line in reversed(lines) if line.strip()), "")


def raise_for_session(returncode: int, output: bytes, record: MeasureRecord | None) -> None:
    """The Measurement is the Baseline: raise unless the session passed and wrote its record."""
    if returncode == _NO_TESTS_EXIT:
        raise MeasurementFailed(no_tests=True)
    if returncode != 0 or record is None:
        failed = record.failed if record is not None else ()
        raise MeasurementFailed(failing_node_ids=failed, reason=_failure_reason(returncode, output))


def _run_session(request: MeasureRequest, files: dict[str, str]) -> tuple[subprocess.CompletedProcess, float]:
    include = [_canonical(os.path.join(request.cwd, path)) for path in request.target_files]
    with open(files["config_file"], "w") as f:
        json.dump({"data_file": files["data_file"], "record_file": files["record_file"], "include": include}, f)
    argv = [
        sys.executable,
        "-c",
        _BOOTSTRAP,
        files["config_file"],
        *request.pytest_args,
        *neutralising_args(request.pytest_args, cwd=request.cwd),
    ]
    start = time.monotonic()
    result = subprocess.run(argv, cwd=request.cwd, env=_session_env(), capture_output=True)
    return result, time.monotonic() - start


def measure(request: MeasureRequest) -> Measurement:
    """Run the Measurement session once and index what it recorded.

    Raises MeasurementFailed when the suite fails or collects nothing, and
    CoverageCoreRefused when coverage.py ran under sysmon. The session's files
    live in `scratch_dir` and are removed before this returns."""
    files = {
        name: os.path.join(request.scratch_dir, f"measurement.{name}")
        for name in ("config_file", "data_file", "record_file")
    }
    try:
        result, wall = _run_session(request, files)
        record = _read_record(files["record_file"])
        raise_for_session(result.returncode, result.stdout + result.stderr, record)
        data = CoverageData(basename=files["data_file"])
        data.read()
        try:
            return measurement_from(data, record, wall)
        finally:
            data.close(force=True)
    finally:
        for path in files.values():
            with contextlib.suppress(FileNotFoundError):
                os.remove(path)


def measure_in_scratch(
    *,
    cwd: str,
    pytest_args: tuple[str, ...] | list[str],
    target_files: tuple[str, ...],
) -> Measurement:
    """`measure` with its own temporary scratch directory, removed before this returns."""
    with tempfile.TemporaryDirectory(prefix="mutate4py-measurement-") as scratch_dir:
        return measure(
            MeasureRequest(
                cwd=cwd,
                pytest_args=tuple(pytest_args),
                target_files=tuple(target_files),
                scratch_dir=scratch_dir,
            )
        )
