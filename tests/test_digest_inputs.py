"""Unit tests for the digest inputs built from a session record (_digest_inputs.py).

The `digest_project` fixture (tests/_digest_project.py) is a real directory tree;
its record's support set comes from the plugin's own filter.
"""

import dataclasses
import os

import pytest

from mutate4py._digest_inputs import digest_inputs_from

from ._measurement_helpers import measurement_for


@pytest.mark.unit
def test_all_test_files_are_relative_to_rootdir(digest_project):
    inputs = digest_inputs_from(digest_project.record, reach={})

    assert inputs.all_test_files == frozenset({"tests/test_calc.py", "tests/sub/test_more.py"})
    assert inputs.rootdir == digest_project.root


@pytest.mark.unit
def test_each_test_file_carries_the_conftests_of_its_directory_chain(digest_project):
    inputs = digest_inputs_from(digest_project.record, reach={})

    assert inputs.conftests_for["tests/test_calc.py"] == ("tests/conftest.py",)
    assert inputs.conftests_for["tests/sub/test_more.py"] == ("tests/conftest.py",)


@pytest.mark.unit
def test_support_files_are_helpers_under_test_roots_plus_pytest_config_and_lockfile(digest_project):
    inputs = digest_inputs_from(digest_project.record, reach={})

    assert inputs.support_files == frozenset(
        {"tests/factories.py", "tests/helpers/factories.py", "pyproject.toml", "uv.lock"}
    )


def _write(root, files):
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)


@pytest.mark.unit
def test_every_non_python_file_under_the_test_roots_is_a_support_file(digest_project):
    _write(digest_project.root, {"tests/data/rates.json": "{}", "tests/sub/golden.txt": "x", "tests/notes": "y"})

    inputs = digest_inputs_from(digest_project.record, reach={})

    assert {"tests/data/rates.json", "tests/sub/golden.txt", "tests/notes"} <= inputs.support_files


@pytest.mark.unit
def test_a_python_file_no_session_module_imported_is_not_a_support_file(digest_project):
    _write(digest_project.root, {"tests/data/script.py": "x = 1\n"})

    inputs = digest_inputs_from(digest_project.record, reach={})

    assert "tests/data/script.py" not in inputs.support_files


@pytest.mark.unit
def test_bytecode_caches_and_hidden_files_and_directories_are_not_support_files(digest_project):
    _write(
        digest_project.root,
        {
            "tests/__pycache__/test_calc.cpython-312.pyc": "x",
            "tests/.pytest_cache/v/cache/lastfailed": "{}",
            "tests/data/.hidden.json": "{}",
        },
    )

    inputs = digest_inputs_from(digest_project.record, reach={})

    assert inputs.support_files == frozenset(
        {"tests/factories.py", "tests/helpers/factories.py", "pyproject.toml", "uv.lock"}
    )


@pytest.mark.unit
def test_a_non_python_file_outside_the_test_roots_is_not_a_support_file(digest_project):
    _write(digest_project.root, {"src/data.json": "{}", "acceptance/steps/table.json": "{}", "notes.txt": "x"})

    inputs = digest_inputs_from(digest_project.record, reach={})

    assert not {"src/data.json", "acceptance/steps/table.json", "notes.txt"} & inputs.support_files


@pytest.mark.unit
def test_a_test_file_in_the_rootdir_itself_makes_no_directory_a_test_root(digest_project):
    _write(digest_project.root, {"test_top.py": "", "src/data.json": "{}", "data.json": "{}"})
    record = dataclasses.replace(digest_project.record, test_files=(str(digest_project.root / "test_top.py"),))

    inputs = digest_inputs_from(record, reach={})

    assert not {"src/data.json", "data.json"} & inputs.support_files


@pytest.mark.unit
def test_acceptance_helpers_and_source_files_never_enter_the_support_set(digest_project):
    inputs = digest_inputs_from(digest_project.record, reach={})

    assert not any(rel.startswith("acceptance/") for rel in inputs.support_files)
    assert "src/calc.py" not in inputs.support_files


@pytest.mark.unit
def test_lockfile_is_left_out_when_the_project_has_none(digest_project):
    (digest_project.root / "uv.lock").unlink()

    inputs = digest_inputs_from(digest_project.record, reach={})

    assert "uv.lock" not in inputs.support_files


@pytest.mark.unit
def test_reach_is_passed_through_unchanged(digest_project):
    reach = {"/proj/src/calc.py": {2: frozenset({"tests/test_calc.py"})}}

    inputs = digest_inputs_from(digest_project.record, reach=reach)

    assert inputs.reach == reach


@pytest.mark.unit
def test_measurement_reach_maps_each_covered_line_to_the_test_files_that_reached_it(digest_project):
    src = str(digest_project.root / "src" / "calc.py")
    measurement = measurement_for(
        src,
        {"tests/test_calc.py::test_f": [2], "tests/sub/test_more.py::test_g": [2], "": [1]},
        record=digest_project.record,
    )

    inputs = measurement.digest_inputs()

    assert inputs.reach[os.path.realpath(src)] == {
        1: frozenset(),
        2: frozenset({"tests/test_calc.py", "tests/sub/test_more.py"}),
    }
    assert inputs.all_test_files == frozenset({"tests/test_calc.py", "tests/sub/test_more.py"})


@pytest.mark.unit
def test_a_manifest_sidecar_is_never_a_support_file(digest_project):
    _write(digest_project.root, {"tests/data/calc.py.manifest.json": "{}", "tests/data/rates.json": "{}"})

    inputs = digest_inputs_from(digest_project.record, reach={})

    assert "tests/data/rates.json" in inputs.support_files
    assert "tests/data/calc.py.manifest.json" not in inputs.support_files


@pytest.mark.unit
def test_a_manifest_sidecar_next_to_code_is_never_a_support_file(digest_project):
    _write(digest_project.root, {"pkg/test_calc.py": "", "pkg/calc.py.manifest.json": "{}", "pkg/rates.json": "{}"})
    record = dataclasses.replace(digest_project.record, test_files=(str(digest_project.root / "pkg/test_calc.py"),))

    inputs = digest_inputs_from(record, reach={})

    assert "pkg/rates.json" in inputs.support_files
    assert "pkg/calc.py.manifest.json" not in inputs.support_files


@pytest.mark.unit
def test_the_walk_stops_at_the_test_folder_of_the_app_that_holds_the_tests(digest_project):
    _write(
        digest_project.root,
        {
            "apps/a/tests/unit/test_x.py": "",
            "apps/a/tests/data/rates.json": "{}",
            "apps/a/settings.json": "{}",
            "apps/b/tests/data/rates.json": "{}",
            "apps/b/settings.json": "{}",
        },
    )
    record = dataclasses.replace(
        digest_project.record, test_files=(str(digest_project.root / "apps/a/tests/unit/test_x.py"),)
    )

    inputs = digest_inputs_from(record, reach={})

    assert "apps/a/tests/data/rates.json" in inputs.support_files
    assert not {"apps/a/settings.json", "apps/b/tests/data/rates.json", "apps/b/settings.json"} & inputs.support_files
