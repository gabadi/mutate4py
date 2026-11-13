"""A real directory tree for the digest tests, and the record a session would write for it.

The record's support set comes from the plugin's own filter (`_support_modules`), so
acceptance criterion (d) is checked against the production rule, not a copy of it.
Test modules import the `digest_project` fixture from here.
"""

from dataclasses import dataclass
from pathlib import Path

import pytest

from mutate4py._measure_record import MeasureRecord, SessionFacts, _support_modules

from ._measurement_helpers import record_for

_FILES = {
    "pyproject.toml": '[tool.pytest.ini_options]\naddopts = "-q"\n',
    "uv.lock": "version = 1\n",
    "src/calc.py": "def f(a):\n    return a + 1\n",
    "tests/conftest.py": "import pytest\n",
    "tests/test_calc.py": "def test_f():\n    assert True\n",
    "tests/sub/test_more.py": "def test_g():\n    assert True\n",
    "tests/factories.py": "def build():\n    return 2\n",
    "tests/helpers/factories.py": "def make():\n    return 1\n",
    "acceptance/steps/calc_helpers.py": "def helper():\n    return 3\n",
}
_TEST_FILES = ("tests/test_calc.py", "tests/sub/test_more.py")
_CONFTESTS = ("tests/conftest.py",)


@dataclass(frozen=True)
class DigestProject:
    root: Path
    record: MeasureRecord


@pytest.fixture
def digest_project(tmp_path) -> DigestProject:
    root = tmp_path / "proj"
    for rel, text in _FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    facts = SessionFacts(
        core="ctrace",
        collected=2,
        args=("tests",),
        rootdir=str(root),
        inipath=str(root / "pyproject.toml"),
        plugin_files=(),
        module_files=tuple(str(root / rel) for rel in _FILES if rel.endswith(".py")),
        test_files=tuple(str(root / rel) for rel in _TEST_FILES),
    )
    conftests = tuple(str(root / rel) for rel in _CONFTESTS)
    record = record_for(
        rootdir=str(root),
        inipath=str(root / "pyproject.toml"),
        test_files=tuple(str(root / rel) for rel in _TEST_FILES),
        conftests=conftests,
        support_modules=_support_modules(facts, conftests),
    )
    return DigestProject(root=root, record=record)
