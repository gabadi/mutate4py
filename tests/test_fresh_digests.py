"""Unit tests for the fresh tests digest of each function in a measured file (_fresh_digests.py).

Each test measures a real directory tree (tests/_digest_project.py) and changes one
input on disk between two digests, so the expected values are the rule's own
statement: which file change moves which function's digest.
"""

import pytest

from mutate4py._fresh_digests import fresh_digests

from ._measurement_helpers import measurement_for

_CLEAN_CALC = "def f(a):\n    return a + 1\n\n\ndef g(a):\n    return a - 1\n"


def _measured(project, lines_by_context):
    """Write the clean source to the project and measure it with the given coverage."""
    src = project.root / "src" / "calc.py"
    src.write_text(_CLEAN_CALC)
    return measurement_for(str(src), lines_by_context, record=project.record), str(src)


@pytest.mark.unit
def test_fresh_digest_is_keyed_by_function_id(digest_project):
    measurement, src = _measured(
        digest_project, {"tests/test_calc.py::test_f": [2], "tests/sub/test_more.py::test_g": [6]}
    )

    assert set(fresh_digests(measurement, src, _CLEAN_CALC)) == {"func/f", "func/g"}


@pytest.mark.unit
def test_digest_changes_when_a_test_reaching_the_function_changes(digest_project):
    measurement, src = _measured(
        digest_project, {"tests/test_calc.py::test_f": [2], "tests/sub/test_more.py::test_g": [6]}
    )
    before = fresh_digests(measurement, src, _CLEAN_CALC)

    (digest_project.root / "tests" / "test_calc.py").write_text("def test_f():\n    assert 1 == 1\n")
    after = fresh_digests(measurement, src, _CLEAN_CALC)

    assert after["func/f"] != before["func/f"]
    assert after["func/g"] == before["func/g"]


@pytest.mark.unit
def test_static_site_digests_every_collected_test_file(digest_project):
    # Line 2 was reached only at import time, so no named test reached it.
    measurement, src = _measured(digest_project, {"": [2], "tests/sub/test_more.py::test_g": [6]})
    before = fresh_digests(measurement, src, _CLEAN_CALC)

    (digest_project.root / "tests" / "sub" / "test_more.py").write_text("def test_g():\n    assert 2 == 2\n")
    after = fresh_digests(measurement, src, _CLEAN_CALC)

    assert after["func/f"] != before["func/f"]


@pytest.mark.unit
def test_support_helper_under_test_root_changes_every_function_digest(digest_project):
    measurement, src = _measured(
        digest_project, {"tests/test_calc.py::test_f": [2], "tests/sub/test_more.py::test_g": [6]}
    )
    before = fresh_digests(measurement, src, _CLEAN_CALC)

    (digest_project.root / "tests" / "factories.py").write_text("def build():\n    return 5\n")
    after = fresh_digests(measurement, src, _CLEAN_CALC)

    assert after["func/f"] != before["func/f"]
    assert after["func/g"] != before["func/g"]


@pytest.mark.unit
def test_acceptance_helper_change_leaves_every_function_digest_unchanged(digest_project):
    measurement, src = _measured(
        digest_project, {"tests/test_calc.py::test_f": [2], "tests/sub/test_more.py::test_g": [6]}
    )
    before = fresh_digests(measurement, src, _CLEAN_CALC)

    (digest_project.root / "acceptance" / "steps" / "calc_helpers.py").write_text("def helper():\n    return 99\n")
    after = fresh_digests(measurement, src, _CLEAN_CALC)

    assert after == before
