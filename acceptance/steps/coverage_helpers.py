"""Pure helpers for coverage acceptance step files.

A run measures coverage itself (ADR 0027), so the scenarios build real pytest
projects. The fixture texts and assertions live here, with unit tests in
tests/test_coverage_helpers.py.
"""

import os

REMOVED_FLAG_MESSAGE = "removed in 0.3.0: the run measures coverage itself"

# Each coverage flag removed in 0.3.0, keyed by its feature row, as the tokens that supply it.
REMOVED_FLAG_TOKENS = {
    "--cov-cmd CMD": ["--cov-cmd", "true"],
    "--lcov cov.info": ["--lcov", "cov.info"],
    "--reuse-coverage": ["--reuse-coverage"],
}

# A conftest.py that imports the module while pytest loads it. Its lines run before
# any test starts, so they are recorded under the Empty context.
IMPORTING_CONFTEST = "import sample  # noqa: F401\n"

# A module whose only site is a module-level line: it runs when the module is imported.
IMPORT_TIME_SOURCE = "A = 3\nB = A + 1\n"

# A function whose comparison is on line 2 of a two-armed branch.
HALF_TAKEN_BRANCH_SOURCE = "def f1(a, b):\n    if a > b:\n        return 1\n    return 0\n"

# Takes only the arm where the comparison is false: the other arm never runs.
HALF_TAKEN_BRANCH_TEST = "import sample\n\n\ndef test_one_arm():\n    assert sample.f1(0, 1) == 0\n"

PASSING_TEST = "def test_qa():\n    pass\n"


def step_param(m, params: dict, key: str) -> str:
    """Return params[key] if present, else m.group(1): the standard step param lookup."""
    return params.get(key) or m.group(1)


def called_names(names_str: str) -> list[str]:
    """The function names a feature row lists, comma separated; an empty cell lists none."""
    return [name.strip() for name in names_str.split(",") if name.strip()]


def removed_flag_tokens(description: str) -> list[str]:
    """The CLI tokens that supply the removed flag a feature row describes."""
    if description not in REMOVED_FLAG_TOKENS:
        raise NotImplementedError(f"Unknown removed flag: {description!r}")
    return REMOVED_FLAG_TOKENS[description]


def removed_flag_refusal(description: str) -> str:
    """The refusal line a removed flag prints: the bare flag name, then the replacement message."""
    return f"{removed_flag_tokens(description)[0]} {REMOVED_FLAG_MESSAGE}"


def core_recording_test(record_path: str) -> str:
    """A test that appends the COVERAGE_CORE it ran under to `record_path`."""
    return (
        "import os\n\n\n"
        "def test_core():\n"
        f"    with open({record_path!r}, 'a') as f:\n"
        "        f.write(os.environ.get('COVERAGE_CORE', '(unset)') + '\\n')\n"
    )


def first_recorded_core(record_path: str) -> str:
    """The core the first recorded run saw: the Measurement runs before any Mutant."""
    assert os.path.exists(record_path), f"no run recorded its coverage core at {record_path}"
    with open(record_path) as f:
        lines = f.read().splitlines()
    assert lines, f"{record_path} is empty"
    return lines[0]


def assert_stdout_contains(result, text: str) -> None:
    assert text in result.stdout, f"expected {text!r} in stdout:\n{result.stdout}\nstderr:\n{result.stderr}"


def assert_stdout_not_contains(result, text: str) -> None:
    assert text not in result.stdout, f"unexpected {text!r} found in stdout:\n{result.stdout}"


def assert_exit_status(result, expected: int) -> None:
    assert result.returncode == expected, (
        f"expected exit {expected}, got {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def assert_output_contains(result, text: str) -> None:
    output = result.stdout + result.stderr
    assert text in output, f"expected {text!r} in the output:\n{output}"


def assert_no_partition_counts(result) -> None:
    assert_stdout_not_contains(result, "Covered mutation sites:")
    assert_stdout_not_contains(result, "Uncovered mutation sites:")


def assert_no_backup_beside(source_path: str) -> None:
    bak = source_path + ".bak"
    assert not os.path.exists(bak), f"unexpected backup file {bak}"
