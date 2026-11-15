"""A scored run records each scored function's tests digest in the Manifest (#105).

These runs take a real Measurement: pytest runs under coverage on a small
project in the run's cwd, so the digest is built from the reach a real session
recorded. Mutants are reported killed by a fake executor, so every function is
scored clean and no test has to tell mutants apart.
"""

import io
import json
import logging
import os
import re
from contextlib import redirect_stdout

import pytest

from ._worker_fakes_helpers import FakeExecutor
from mutate4py._runner import RunMutationsRequest, run_mutations

SRC = "def f(a, b):\n    return a > b\n"
# Imports the function, so its one Site is reached by a real test.
TEST_CALC = "from calc import f\n\n\ndef test_gt():\n    assert f(2, 1) is True\n"


def _write_project(tmp_path) -> str:
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(SRC)
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_calc.py").write_text(TEST_CALC)
    return src_path


def _on_disk(src_path: str) -> str:
    with open(src_path) as f:
        return f.read()


def _run(
    src_path: str,
    executor: FakeExecutor,
    *,
    manifest_file: bool,
    allow_survivors: bool = False,
    pytest_args: tuple[str, ...] = ("-q", "tests"),
) -> int:
    request = RunMutationsRequest(
        path=src_path,
        source=_on_disk(src_path),
        pytest_args=list(pytest_args),
        timeout_factor=10,
        warning_threshold=1000,
        cwd=os.path.dirname(src_path),
        executor=executor,
        manifest_file=manifest_file,
        allow_survivors=allow_survivors,
    )
    with redirect_stdout(io.StringIO()):
        return run_mutations(request)


def _manifest_of(src_path: str, *, manifest_file: bool) -> dict:
    """The Manifest as stored: the sidecar JSON, or the footer line of the source."""
    if manifest_file:
        with open(src_path + ".manifest.json") as f:
            return json.load(f)
    footer = [ln for ln in _on_disk(src_path).splitlines() if ln.startswith("# {")][0]
    return json.loads(footer[2:])


def _forget_digests(src_path: str, *, manifest_file: bool) -> None:
    """Store the Manifest as a 0.2.x run left it: no tests_digest on any entry."""
    manifest = _manifest_of(src_path, manifest_file=manifest_file)
    for fn in manifest["functions"]:
        fn.pop("tests_digest", None)
    if manifest_file:
        with open(src_path + ".manifest.json", "w") as f:
            json.dump(manifest, f)
        return
    lines = [
        f"# {json.dumps(manifest)}\n" if ln.startswith("# {") else ln for ln in _on_disk(src_path).splitlines(True)
    ]
    with open(src_path, "w") as f:
        f.write("".join(lines))


@pytest.mark.system
@pytest.mark.parametrize("manifest_file", [False, True], ids=["footer", "sidecar"])
def test_a_scored_run_records_the_tests_digest_of_each_scored_function(tmp_path, manifest_file):
    src_path = _write_project(tmp_path)
    executor = FakeExecutor("killed")

    rc = _run(src_path, executor, manifest_file=manifest_file)

    assert rc == 0
    assert executor.calls, "the function must be scored in this run"
    (fn,) = _manifest_of(src_path, manifest_file=manifest_file)["functions"]
    assert fn["id"] == "func/f"
    assert isinstance(fn["tests_digest"], str) and fn["tests_digest"]


@pytest.mark.system
@pytest.mark.parametrize("manifest_file", [False, True], ids=["footer", "sidecar"])
def test_an_unchanged_function_without_a_digest_gains_one_on_a_run_that_does_not_rescore_it(tmp_path, manifest_file):
    src_path = _write_project(tmp_path)
    _run(src_path, FakeExecutor("killed"), manifest_file=manifest_file)
    (first,) = _manifest_of(src_path, manifest_file=manifest_file)["functions"]
    _forget_digests(src_path, manifest_file=manifest_file)
    executor = FakeExecutor("killed")

    rc = _run(src_path, executor, manifest_file=manifest_file)

    assert rc == 0
    assert executor.calls == [], "an unchanged, Survivor-free function is not rescored"
    (fn,) = _manifest_of(src_path, manifest_file=manifest_file)["functions"]
    assert fn["tests_digest"] == first["tests_digest"]
    assert fn["score"] == first["score"]


ACCEPTANCE_STEPS = "STEP = 'first'\n"
OUTSIDE_HELPER = "VALUE = 'first'\n"
CALC_SUPPORT = "LABEL = 'first'\n"
# Imports all three helpers, so each one is among the session's modules. Only the support module
# under tests/ may enter the digest: the acceptance helper and the file at rootdir must stay out.
TEST_CALC_WITH_HELPERS = (
    "from acceptance import steps\n"
    "from outside_helper import VALUE\n"
    "from calc import f\n"
    "from calc_support import LABEL\n\n\n"
    "def test_gt():\n"
    "    assert f(2, 1) is True\n"
    "    assert steps.STEP and VALUE and LABEL\n"
)


def _write_files(root, files: dict[str, str]) -> None:
    for relpath, text in files.items():
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def _write_project_with_helpers(tmp_path) -> str:
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(SRC)
    _write_files(
        tmp_path,
        {
            "tests/test_calc.py": TEST_CALC_WITH_HELPERS,
            "tests/calc_support.py": CALC_SUPPORT,
            "acceptance/steps.py": ACCEPTANCE_STEPS,
            "outside_helper.py": OUTSIDE_HELPER,
        },
    )
    return src_path


@pytest.mark.system
def test_an_acceptance_helper_or_a_file_outside_the_test_roots_never_changes_the_digest(tmp_path):
    src_path = _write_project_with_helpers(tmp_path)
    _run(src_path, FakeExecutor("killed"), manifest_file=False)
    (first,) = _manifest_of(src_path, manifest_file=False)["functions"]
    _forget_digests(src_path, manifest_file=False)
    _write_files(
        tmp_path,
        {
            "acceptance/steps.py": "STEP = 'second, and longer'\n",
            "outside_helper.py": "VALUE = 'second, and longer'\n",
        },
    )
    executor = FakeExecutor("killed")

    rc = _run(src_path, executor, manifest_file=False)

    assert rc == 0
    assert executor.calls == [], "an unchanged, Survivor-free function is not rescored"
    (second,) = _manifest_of(src_path, manifest_file=False)["functions"]
    assert second["tests_digest"] == first["tests_digest"]


@pytest.mark.system
@pytest.mark.parametrize(
    ("relpath", "text"),
    [
        ("tests/calc_support.py", "LABEL = 'second, and longer'\n"),
        ("tests/test_calc.py", TEST_CALC_WITH_HELPERS.replace("f(2, 1)", "f(3, 1)")),
    ],
    ids=["support-module-under-the-tests", "reaching-test"],
)
def test_a_digestless_entry_adopts_a_test_root_change_as_its_digest_without_rescoring(tmp_path, relpath, text):
    src_path = _write_project_with_helpers(tmp_path)
    _run(src_path, FakeExecutor("killed"), manifest_file=False)
    (first,) = _manifest_of(src_path, manifest_file=False)["functions"]
    _forget_digests(src_path, manifest_file=False)
    _write_files(tmp_path, {relpath: text})
    executor = FakeExecutor("killed")

    rc = _run(src_path, executor, manifest_file=False)

    assert rc == 0
    assert executor.calls == [], "an unchanged, Survivor-free function is not rescored"
    (second,) = _manifest_of(src_path, manifest_file=False)["functions"]
    assert second["tests_digest"] != first["tests_digest"]


# ── #106: a stored digest that changes re-scores its function; the skip rule ──

# Two functions, each reached by its own test file, so a test can tell which
# FunctionIDs a run re-scored from the per-Mutant progress lines.
TWO_FUNCTIONS = "def f(a, b):\n    return a > b\n\n\ndef g(a, b):\n    return a > b\n"
TEST_F = "from calc import f\n\n\ndef test_f():\n    assert f(2, 1) is True\n"
TEST_G = "from calc import g\n\n\ndef test_g():\n    assert g(2, 1) is True\n"
TEST_UNRELATED = "def test_unrelated():\n    assert 1 + 1 == 2\n"
# Imports both functions and calls neither: its reach is the two def lines only.
TEST_IMPORT_ONLY = "from calc import f, g\n\n\ndef test_nothing():\n    pass\n"
_PROGRESS_FID = re.compile(r"^\[\d+/\d+\] \S+ line \d+ .*: (\S+)$")


def _write_two_function_project(tmp_path) -> str:
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(TWO_FUNCTIONS)
    _write_files(tmp_path, {"tests/test_f.py": TEST_F, "tests/test_g.py": TEST_G})
    return src_path


def _digests(src_path: str) -> dict[str, str]:
    return {fn["id"]: fn["tests_digest"] for fn in _manifest_of(src_path, manifest_file=False)["functions"]}


def _rescored_ids(caplog) -> set[str]:
    """The FunctionIDs whose Mutants ran in the run, read from its per-Mutant progress lines."""
    lines = [line for record in caplog.records for line in record.getMessage().splitlines()]
    return {m.group(1) for m in (_PROGRESS_FID.match(line) for line in lines) if m}


@pytest.mark.system
def test_an_edit_to_a_test_that_reaches_a_function_re_scores_only_that_function(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    src_path = _write_two_function_project(tmp_path)
    _run(src_path, FakeExecutor("killed"), manifest_file=False)
    first = _digests(src_path)
    _write_files(tmp_path, {"tests/test_f.py": TEST_F.replace("f(2, 1)", "f(3, 1)")})
    caplog.clear()

    rc = _run(src_path, FakeExecutor("killed"), manifest_file=False)

    assert rc == 0
    assert _rescored_ids(caplog) == {"func/f"}
    second = _digests(src_path)
    assert second["func/f"] != first["func/f"]
    assert second["func/g"] == first["func/g"]


@pytest.mark.system
@pytest.mark.parametrize(
    ("relpath", "text"),
    [
        ("tests/test_calc.py", TEST_CALC_WITH_HELPERS.replace("f(2, 1)", "f(3, 1)")),
        ("tests/calc_support.py", "LABEL = 'second, and longer'\n"),
        ("tests/conftest.py", "CONF = 'second'\n"),
    ],
    ids=["reaching-test", "factories-helper-under-the-tests", "conftest"],
)
def test_an_edit_under_the_test_roots_re_scores_the_function_it_reaches(tmp_path, caplog, relpath, text):
    caplog.set_level(logging.INFO)
    src_path = _write_project_with_helpers(tmp_path)
    _write_files(tmp_path, {"tests/conftest.py": "CONF = 'first'\n"})
    _run(src_path, FakeExecutor("killed"), manifest_file=False)
    first = _digests(src_path)
    _write_files(tmp_path, {relpath: text})
    caplog.clear()

    rc = _run(src_path, FakeExecutor("killed"), manifest_file=False)

    assert rc == 0
    assert _rescored_ids(caplog) == {"func/f"}
    assert _digests(src_path)["func/f"] != first["func/f"]


@pytest.mark.system
def test_a_file_outside_the_test_roots_re_scores_nothing_once_a_digest_is_stored(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    src_path = _write_project_with_helpers(tmp_path)
    _run(src_path, FakeExecutor("killed"), manifest_file=False)
    first = _digests(src_path)
    _write_files(
        tmp_path,
        {
            "acceptance/steps.py": "STEP = 'second, and longer'\n",
            "outside_helper.py": "VALUE = 'second, and longer'\n",
        },
    )
    caplog.clear()

    rc = _run(src_path, FakeExecutor("killed"), manifest_file=False)

    assert rc == 0
    assert _rescored_ids(caplog) == set()
    assert _digests(src_path) == first


@pytest.mark.system
def test_an_unrelated_test_edit_re_scores_nothing(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    src_path = _write_two_function_project(tmp_path)
    _write_files(tmp_path, {"tests/test_unrelated.py": TEST_UNRELATED})
    _run(src_path, FakeExecutor("killed"), manifest_file=False)
    first = _digests(src_path)
    _write_files(tmp_path, {"tests/test_unrelated.py": TEST_UNRELATED.replace("1 + 1", "2 + 0")})
    caplog.clear()

    rc = _run(src_path, FakeExecutor("killed"), manifest_file=False)

    assert rc == 0
    assert _rescored_ids(caplog) == set()
    assert _digests(src_path) == first


@pytest.mark.system
def test_an_edit_to_a_test_file_whose_tests_are_all_deselected_re_scores_nothing(tmp_path, caplog):
    """A deselected test module is imported to collect it, but it is a test file, not a helper (#110)."""
    caplog.set_level(logging.INFO)
    src_path = _write_two_function_project(tmp_path)
    slow = "from calc import f\n\n\ndef test_slow():\n    assert f(2, 1) is True\n"
    _write_files(tmp_path, {"tests/test_slow.py": slow})
    args = ("-q", "tests", "-k", "not slow")
    _run(src_path, FakeExecutor("killed"), manifest_file=False, pytest_args=args)
    first = _digests(src_path)
    _write_files(tmp_path, {"tests/test_slow.py": slow.replace("f(2, 1)", "f(3, 1)")})
    caplog.clear()

    rc = _run(src_path, FakeExecutor("killed"), manifest_file=False, pytest_args=args)

    assert rc == 0
    assert _rescored_ids(caplog) == set()
    assert _digests(src_path) == first


@pytest.mark.system
def test_a_definition_line_only_reach_change_re_scores_nothing(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    src_path = _write_two_function_project(tmp_path)
    _write_files(tmp_path, {"tests/test_import_only.py": TEST_IMPORT_ONLY})
    _run(src_path, FakeExecutor("killed"), manifest_file=False)
    first = _digests(src_path)
    _write_files(tmp_path, {"tests/test_import_only.py": TEST_IMPORT_ONLY.replace("pass", "pass  # edited")})
    caplog.clear()

    rc = _run(src_path, FakeExecutor("killed"), manifest_file=False)

    assert rc == 0
    assert _rescored_ids(caplog) == set()
    assert _digests(src_path) == first


@pytest.mark.system
@pytest.mark.parametrize("manifest_file", [False, True], ids=["footer", "sidecar"])
def test_a_0_2_x_entry_with_survivors_is_re_scored_once_then_skipped(tmp_path, manifest_file):
    src_path = _write_project(tmp_path)
    assert _run(src_path, FakeExecutor("survived"), manifest_file=manifest_file) == 3
    _forget_digests(src_path, manifest_file=manifest_file)
    once = FakeExecutor("survived")

    assert _run(src_path, once, manifest_file=manifest_file) == 3
    assert once.calls, "a 0.2.x entry with recorded survivors is re-scored once"
    (fn,) = _manifest_of(src_path, manifest_file=manifest_file)["functions"]
    assert isinstance(fn["tests_digest"], str) and fn["tests_digest"]

    skipped = FakeExecutor("survived")
    assert _run(src_path, skipped, manifest_file=manifest_file) == 3
    assert skipped.calls == [], "once it has a digest, an unchanged function with survivors is skipped"


@pytest.mark.system
@pytest.mark.parametrize(
    ("allow_survivors", "rc"),
    [(False, 3), (True, 0)],
    ids=["gate", "allow-survivors"],
)
def test_recorded_survivors_of_a_skipped_function_print_apart_and_count_toward_the_exit_code(
    tmp_path, caplog, allow_survivors, rc
):
    caplog.set_level(logging.INFO)
    src_path = _write_two_function_project(tmp_path)
    _run(src_path, FakeExecutor("survived"), manifest_file=False)
    # Editing g's body moves its hash, so g is re-scored and f, unchanged, is skipped.
    # The edit goes into the file as it stands, so the Manifest footer run 1 wrote survives it.
    with open(src_path) as f:
        current = f.read()
    with open(src_path, "w") as f:
        f.write(current.replace("def g(a, b):\n    return a > b", "def g(a, b):\n    return a >= b"))
    caplog.clear()

    got = _run(src_path, FakeExecutor("survived"), manifest_file=False, allow_survivors=allow_survivors)

    assert got == rc
    report = caplog.text
    this_run, marker, recorded = report.partition("Recorded survivors (function unchanged, not re-run):")
    assert marker, "the recorded survivors print in their own block"
    assert "func/g" in this_run and "Survivors:" in this_run
    assert "func/f" not in this_run
    assert "  line 2 a > b -> a >= b func/f" in recorded
    assert "func/g" not in recorded
