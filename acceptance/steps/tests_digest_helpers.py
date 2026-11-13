"""Pure helpers for the tests-digest acceptance steps.

The steps score real pytest projects through the CLI, edit one file and score again. These
helpers hold what has no filesystem or subprocess coupling: the project's file texts, the
edit that changes a file's content, and the parsing of a run's report into the FunctionIDs
it re-scored and the Survivors it only recorded. Unit tests: tests/test_tests_digest_helpers.py.
"""

import json
import re

RECORDED_HEADER = "Recorded survivors (not re-run):"

# One module per case the digest has to get right. Each function is killed by its own tests,
# so a run's progress lines name exactly the functions it re-scored.
DIGEST_PROJECT_FILES = {
    "pyproject.toml": (
        '[project]\nname = "digest-project"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
        'dependencies = []\n\n[tool.pytest.ini_options]\npythonpath = ["src", "tests", "."]\n'
        'testpaths = ["tests"]\n'
    ),
    "src/alpha.py": "def inc(a, b):\n    return a + b\n\n\ndef dec(a, b):\n    return a - b\n",
    "src/beta.py": "def big(a, b):\n    return a > b\n",
    "src/gamma.py": "def shrink(a, b):\n    return a - b\n",
    "src/delta.py": "def twice(a):\n    return a * 2\n",
    "src/eps.py": "def shift(a):\n    return a + 1\n",
    # alpha: its tests sit under a conftest of their own.
    "tests/pkg_a/conftest.py": "import pytest\n\n\n@pytest.fixture\ndef pair():\n    return (3, 2)\n",
    "tests/pkg_a/test_alpha.py": (
        "from alpha import dec, inc\n\n\ndef test_inc(pair):\n    assert inc(*pair) == 5\n\n\n"
        "def test_dec(pair):\n    assert dec(*pair) == 1\n"
    ),
    # beta: a factory module that sits in the tests directory.
    "tests/factories.py": "def operands():\n    return (2, 1)\n",
    "tests/test_beta.py": (
        "from beta import big\nfrom factories import operands\n\n\ndef test_big():\n"
        "    a, b = operands()\n    assert big(a, b)\n    assert not big(b, a)\n    assert not big(a, a)\n"
    ),
    # gamma: a helper in a directory beside the test's own, reached through a package path.
    "tests/helpers/builders.py": "def pair():\n    return (3, 2)\n",
    "tests/unit/test_gamma.py": (
        "from gamma import shrink\nfrom helpers.builders import pair\n\n\ndef test_shrink():\n"
        "    assert shrink(*pair()) == 1\n"
    ),
    # delta: one test only loads the module, another one calls the function.
    "tests/test_delta_a_load.py": "def test_loads():\n    import delta  # noqa: F401\n",
    "tests/test_delta_b_call.py": "def test_calls():\n    import delta\n\n    assert delta.twice(2) == 4\n",
    # eps: a helper that sits outside every test root.
    "tools/stamp.py": "def expected():\n    return 2\n",
    "tests/test_eps.py": "from eps import shift\nfrom tools.stamp import expected\n\n\ndef test_shift():\n    assert shift(1) == expected()\n",
    "tests/test_other.py": "def test_unrelated():\n    assert 1 + 1 == 2\n",
}

SURVIVOR_PROJECT_FILES = {
    "pyproject.toml": (
        '[project]\nname = "survivor-project"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
        'dependencies = []\n\n[tool.pytest.ini_options]\npythonpath = ["."]\ntestpaths = ["tests"]\n'
    ),
    "sur.py": "def keep(a, b):\n    return a > b\n\n\ndef other(a, b):\n    return a > b\n",
    "tests/test_sur.py": (
        "import sur\n\n\ndef test_keep():\n    assert sur.keep(2, 1)\n\n\n"
        "def test_other():\n    assert sur.other(2, 1)\n"
    ),
}

# The edit that gives `other` a new hash while its `>=` Mutant still survives.
OTHER_BEFORE = "def other(a, b):\n    return a > b"
OTHER_AFTER = "def other(a, b):\n    return a > b + 0"

_PROGRESS = re.compile(r"^\[\d+/\d+\] .*: (\S+)$")
_SURVIVOR_ROW = re.compile(r"^  line \d+ .* (\S+)$")


def edited(text: str) -> str:
    """The same file with one more comment line: different bytes, same behaviour."""
    return text + "# edited\n"


def rescored_function_ids(stdout: str) -> list[str]:
    """The FunctionIDs a run re-scored, in order and without repeats, read from its progress lines."""
    found: list[str] = []
    for line in stdout.splitlines():
        hit = _PROGRESS.match(line)
        if hit and hit.group(1) not in found:
            found.append(hit.group(1))
    return found


def _block_ids(stdout: str, header: str) -> list[str]:
    """The FunctionIDs on the indented rows that follow a header line, in order and without repeats."""
    found: list[str] = []
    lines = stdout.splitlines()
    if header not in lines:
        return found
    for line in lines[lines.index(header) + 1 :]:
        hit = _SURVIVOR_ROW.match(line)
        if not hit:
            break
        if hit.group(1) not in found:
            found.append(hit.group(1))
    return found


def survivor_ids(stdout: str) -> list[str]:
    """The FunctionIDs under the run's own `Survivors:` block."""
    return _block_ids(stdout, "Survivors:")


def recorded_survivor_ids(stdout: str) -> list[str]:
    """The FunctionIDs under the `Recorded survivors (not re-run):` block."""
    return _block_ids(stdout, RECORDED_HEADER)


def without_digests(source: str) -> str:
    """The source with its embedded Manifest as a 0.2.x run left it: no tests_digest on any entry."""
    out = []
    for line in source.splitlines(keepends=True):
        if line.startswith("# {"):
            manifest = json.loads(line[2:])
            for fn in manifest["functions"]:
                fn.pop("tests_digest", None)
            line = f"# {json.dumps(manifest)}\n"
        out.append(line)
    return "".join(out)
