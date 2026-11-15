from pathlib import Path
from types import SimpleNamespace

import pytest

from tests import conftest

UNIT = pytest.mark.unit.mark


class _Item:
    def __init__(self, *, own: list, inherited: list):
        self.nodeid = "tests/test_probe.py::test_probe"
        self.path = Path(__file__)
        self.own_markers = own
        self._inherited = inherited

    def iter_markers(self, name=None):
        return iter(m for m in self.own_markers + self._inherited if name is None or m.name == name)


def _report_after_call(item: _Item) -> SimpleNamespace:
    report = SimpleNamespace(outcome="passed", longrepr=None)
    hook = conftest.pytest_runtest_makereport(item, SimpleNamespace(when="call", duration=0.01))
    next(hook)
    with pytest.raises(StopIteration):
        hook.send(SimpleNamespace(get_result=lambda: report))
    return report


@pytest.mark.unit
def test_a_category_marker_inherited_from_a_module_pytestmark_fails_the_test():
    report = _report_after_call(_Item(own=[], inherited=[UNIT]))

    assert report.outcome == "failed"
    assert "has no @pytest.mark.{unit,system}" in report.longrepr


@pytest.mark.unit
def test_a_category_marker_on_the_test_itself_passes_the_guard():
    report = _report_after_call(_Item(own=[UNIT], inherited=[]))

    assert report.outcome == "passed"
