"""The pytest plugin inside the Measurement session.

Boundary code: it runs only in the spawned Measurement session, which measures
only the Mutation target files, so no Mutant run ever sees it. Keep it to
forwarding pytest's hooks; the decisions live in `_measure_record`, which has
unit tests. `_measurement`'s bootstrap starts coverage.py, then imports this
module and hands the plugin the running `Coverage` object.
"""

import sys
import time

import pytest

from mutate4py._measure_record import SessionFacts, SessionLog, core_from_sys_info, dump_record

__all__ = ["MeasurePlugin"]


class MeasurePlugin:
    def __init__(self, cov, record_path: str) -> None:
        self._cov = cov
        self._record_path = record_path
        self._log = SessionLog()
        self._items: list = []
        self._deselected: set[str] = set()

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_protocol(self, item, nextitem):
        # One context per test, spanning setup, call and teardown: lines run
        # between tests fall back to the Empty context.
        self._log.test_started(item.nodeid, item.fixturenames)
        self._cov.switch_context(item.nodeid)
        try:
            return (yield)
        finally:
            self._cov.switch_context("")

    @pytest.hookimpl(wrapper=True)
    def pytest_fixture_setup(self, fixturedef, request):
        start = time.perf_counter()
        try:
            return (yield)
        finally:
            self._log.fixture_set_up(fixturedef.argname, fixturedef.scope, time.perf_counter() - start)

    def pytest_runtest_logreport(self, report) -> None:
        self._log.test_phase(report.nodeid, report.when, report.duration, failed=report.failed)

    def pytest_collectreport(self, report) -> None:
        if report.failed:
            self._log.collection_failed(report.nodeid)

    def pytest_deselected(self, items) -> None:
        self._deselected.update(str(item.path) for item in items)

    def pytest_collection_finish(self, session) -> None:
        self._items = list(session.items)

    def pytest_sessionfinish(self, session) -> None:
        config = session.config
        facts = SessionFacts(
            core=core_from_sys_info(self._cov.sys_info()),
            collected=len(self._items),
            # The explicit positionals only: config.args falls back to the ini
            # testpaths when none were given, which is not what the run was asked for.
            args=tuple(config.known_args_namespace.file_or_dir),
            rootdir=str(config.rootpath),
            inipath=str(config.inipath) if config.inipath else None,
            plugin_files=_files(config.pluginmanager.get_plugins()),
            module_files=_files(list(sys.modules.values())),
            test_files=tuple(sorted({str(item.path) for item in self._items})),
            deselected_files=tuple(sorted(self._deselected)),
        )
        with open(self._record_path, "w") as f:
            f.write(dump_record(self._log.finish(facts)))


def _files(modules) -> tuple[str, ...]:
    return tuple(path for path in (getattr(module, "__file__", None) for module in modules) if isinstance(path, str))
