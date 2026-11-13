"""Unit tests for _tests_digest: the per-function tests digest, over real files in a temp dir."""

import pytest

from mutate4py._tests_digest import DigestInputs, FunctionUnit, function_digest

SRC = "src/app.py"
UNIT = FunctionUnit(path=SRC, function_id="func/handler")


def _write(root, rel, text):
    """Write text to root/rel, creating directories, and return rel."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return rel


def _inputs(root, *, reach=None, all_tests=(), conftests=None, support=()):
    """DigestInputs with every reaching or collected test file given an entry in conftests_for."""
    reaching = {t for by_line in (reach or {}).values() for ts in by_line.values() for t in ts}
    conftests_for = {t: () for t in {*all_tests, *reaching}}
    conftests_for.update(conftests or {})
    return DigestInputs(
        rootdir=root,
        reach=reach or {},
        all_test_files=frozenset(all_tests),
        conftests_for=conftests_for,
        support_files=frozenset(support),
    )


@pytest.mark.unit
def test_reaching_test_file_content_changes_the_digest(tmp_path):
    test_a = _write(tmp_path, "tests/test_app.py", "def test_a():\n    assert handler() == 1\n")
    inputs = _inputs(tmp_path, reach={SRC: {3: frozenset({test_a})}}, all_tests=[test_a])
    before = function_digest(inputs, UNIT, frozenset({3}), frozenset())

    _write(tmp_path, test_a, "def test_a():\n    assert handler() == 2\n")
    after = function_digest(inputs, UNIT, frozenset({3}), frozenset())

    assert before != after


@pytest.mark.unit
def test_test_file_reaching_no_covered_site_line_does_not_change_the_digest(tmp_path):
    test_a = _write(tmp_path, "tests/test_a.py", "def test_a():\n    assert handler()\n")
    test_b = _write(tmp_path, "tests/test_b.py", "def test_b():\n    assert other()\n")
    inputs = _inputs(
        tmp_path,
        reach={SRC: {3: frozenset({test_a})}, "src/other.py": {3: frozenset({test_b})}},
        all_tests=[test_a, test_b],
    )
    before = function_digest(inputs, UNIT, frozenset({3}), frozenset())

    _write(tmp_path, test_b, "def test_b():\n    assert other() is None\n")
    after = function_digest(inputs, UNIT, frozenset({3}), frozenset())

    assert before == after


@pytest.mark.unit
def test_definition_and_decorator_lines_never_add_a_test_file(tmp_path):
    test_def = _write(tmp_path, "tests/test_def.py", "def test_def():\n    pass\n")
    test_body = _write(tmp_path, "tests/test_body.py", "def test_body():\n    assert handler()\n")
    # test_def reaches line 1 (the def/decorator line of handler); only the body Site line 3 is covered.
    reach = {SRC: {1: frozenset({test_def}), 3: frozenset({test_body})}}
    inputs = _inputs(tmp_path, reach=reach, all_tests=[test_def, test_body])
    before = function_digest(inputs, UNIT, frozenset({3}), frozenset())

    _write(tmp_path, test_def, "def test_def():\n    assert True\n")
    after = function_digest(inputs, UNIT, frozenset({3}), frozenset())

    assert before == after


@pytest.mark.unit
def test_every_test_file_reaching_any_covered_site_line_counts(tmp_path):
    test_a = _write(tmp_path, "tests/test_a.py", "def test_a():\n    assert handler()\n")
    test_b = _write(tmp_path, "tests/test_b.py", "def test_b():\n    assert handler()\n")
    reach = {SRC: {3: frozenset({test_a}), 5: frozenset({test_b})}}
    inputs = _inputs(tmp_path, reach=reach, all_tests=[test_a, test_b])
    before = function_digest(inputs, UNIT, frozenset({3, 5}), frozenset())

    _write(tmp_path, test_b, "def test_b():\n    assert handler() == 0\n")
    after = function_digest(inputs, UNIT, frozenset({3, 5}), frozenset())

    assert before != after


@pytest.mark.unit
def test_static_site_line_digests_every_collected_test_file(tmp_path):
    test_a = _write(tmp_path, "tests/test_a.py", "def test_a():\n    pass\n")
    test_b = _write(tmp_path, "tests/test_b.py", "def test_b():\n    pass\n")
    inputs = _inputs(tmp_path, all_tests=[test_a, test_b])
    before = function_digest(inputs, UNIT, frozenset({3}), frozenset({3}))

    _write(tmp_path, test_b, "def test_b():\n    assert True\n")
    after = function_digest(inputs, UNIT, frozenset({3}), frozenset({3}))

    assert before != after


@pytest.mark.unit
def test_reaching_test_file_conftest_is_digested(tmp_path):
    test_a = _write(tmp_path, "tests/test_a.py", "def test_a():\n    assert handler()\n")
    conftest = _write(tmp_path, "tests/conftest.py", "import pytest\n")
    inputs = _inputs(
        tmp_path,
        reach={SRC: {3: frozenset({test_a})}},
        all_tests=[test_a],
        conftests={test_a: (conftest,)},
    )
    before = function_digest(inputs, UNIT, frozenset({3}), frozenset())

    _write(tmp_path, conftest, "import pytest\n\n@pytest.fixture\ndef x():\n    return 1\n")
    after = function_digest(inputs, UNIT, frozenset({3}), frozenset())

    assert before != after


@pytest.mark.unit
def test_conftest_of_a_non_reaching_test_file_is_not_digested(tmp_path):
    test_a = _write(tmp_path, "tests/test_a.py", "def test_a():\n    assert handler()\n")
    test_b = _write(tmp_path, "tests/sub/test_b.py", "def test_b():\n    pass\n")
    sub_conftest = _write(tmp_path, "tests/sub/conftest.py", "import pytest\n")
    inputs = _inputs(
        tmp_path,
        reach={SRC: {3: frozenset({test_a})}},
        all_tests=[test_a, test_b],
        conftests={test_b: (sub_conftest,)},
    )
    before = function_digest(inputs, UNIT, frozenset({3}), frozenset())

    _write(tmp_path, sub_conftest, "import pytest\n\nX = 1\n")
    after = function_digest(inputs, UNIT, frozenset({3}), frozenset())

    assert before == after


@pytest.mark.unit
@pytest.mark.parametrize("support", ["tests/helpers.py", "uv.lock", "pytest.ini"])
def test_support_file_content_changes_the_digest(tmp_path, support):
    test_a = _write(tmp_path, "tests/test_a.py", "def test_a():\n    assert handler()\n")
    _write(tmp_path, support, "x = 1\n")
    inputs = _inputs(tmp_path, reach={SRC: {3: frozenset({test_a})}}, all_tests=[test_a], support=[support])
    before = function_digest(inputs, UNIT, frozenset({3}), frozenset())

    _write(tmp_path, support, "x = 2\n")
    after = function_digest(inputs, UNIT, frozenset({3}), frozenset())

    assert before != after


@pytest.mark.unit
def test_renaming_a_digested_file_changes_the_digest(tmp_path):
    test_a = _write(tmp_path, "tests/test_a.py", "def test_a():\n    assert handler()\n")
    inputs = _inputs(tmp_path, reach={SRC: {3: frozenset({test_a})}}, all_tests=[test_a])
    before = function_digest(inputs, UNIT, frozenset({3}), frozenset())

    renamed = _write(tmp_path, "tests/test_renamed.py", (tmp_path / test_a).read_text(encoding="utf-8"))
    (tmp_path / test_a).unlink()
    inputs = _inputs(tmp_path, reach={SRC: {3: frozenset({renamed})}}, all_tests=[renamed])
    after = function_digest(inputs, UNIT, frozenset({3}), frozenset())

    assert before != after


@pytest.mark.unit
def test_pyproject_digests_only_the_pytest_table(tmp_path):
    test_a = _write(tmp_path, "tests/test_a.py", "def test_a():\n    assert handler()\n")
    pyproject = '[project]\nname = "app"\n\n[tool.pytest.ini_options]\naddopts = "-q"\n'
    _write(tmp_path, "pyproject.toml", pyproject)
    inputs = _inputs(tmp_path, reach={SRC: {3: frozenset({test_a})}}, all_tests=[test_a], support=["pyproject.toml"])
    before = function_digest(inputs, UNIT, frozenset({3}), frozenset())

    _write(tmp_path, "pyproject.toml", pyproject.replace('name = "app"', 'name = "renamed"'))
    assert function_digest(inputs, UNIT, frozenset({3}), frozenset()) == before

    _write(tmp_path, "pyproject.toml", pyproject.replace('"-q"', '"-x"'))
    assert function_digest(inputs, UNIT, frozenset({3}), frozenset()) != before
