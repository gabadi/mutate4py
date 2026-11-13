"""A scored run records each scored function's tests digest in the Manifest (#105).

These runs take a real Measurement: pytest runs under coverage on a small
project in the run's cwd, so the digest is built from the reach a real session
recorded. Mutants are reported killed by a fake executor, so every function is
scored clean and no test has to tell mutants apart.
"""

import io
import json
import os
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


def _run(src_path: str, executor: FakeExecutor, *, manifest_file: bool) -> int:
    request = RunMutationsRequest(
        path=src_path,
        source=_on_disk(src_path),
        pytest_args=["-q", "tests"],
        timeout_factor=10,
        mutate_all=False,
        warning_threshold=1000,
        cwd=os.path.dirname(src_path),
        executor=executor,
        manifest_file=manifest_file,
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


@pytest.mark.component
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


@pytest.mark.component
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


@pytest.mark.component
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


@pytest.mark.component
@pytest.mark.parametrize(
    ("relpath", "text"),
    [
        ("tests/calc_support.py", "LABEL = 'second, and longer'\n"),
        ("tests/test_calc.py", TEST_CALC_WITH_HELPERS.replace("f(2, 1)", "f(3, 1)")),
    ],
    ids=["support-module-under-the-tests", "reaching-test"],
)
def test_a_change_under_the_test_roots_changes_the_digest_on_a_run_that_does_not_rescore(tmp_path, relpath, text):
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
