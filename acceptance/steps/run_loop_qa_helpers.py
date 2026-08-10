"""Pure helpers for features/run-loop_qa.feature's step handlers.

Extracted from run_loop_qa_steps.py so the fake-pytest-test source bodies
(string construction from parameters, no ctx/subprocess coupling) have their
own unit tests, per this repo's boundary-file convention for acceptance step
files.
"""

BODY_ALWAYS_PASS = "def test_qa():\n    pass\n"
BODY_ALWAYS_FAIL = "def test_qa():\n    assert False\n"


def make_lcov(source_abs: str, covered_lines: list[int]) -> str:
    """Build LCOV text marking the given lines covered for source_abs."""
    da = "\n".join(f"DA:{ln},1" for ln in sorted(covered_lines))
    return f"SF:{source_abs}\n{da}\nend_of_record\n"


def write_test(path: str, body: str) -> None:
    with open(path, "w") as f:
        f.write(body)


def mutated_run_exits_nonzero_body(calc_path: str) -> str:
    """Passes on unmutated source; fails when any `>=`/`<=` mutant is present."""
    return (
        "import re\n\n"
        "def test_qa():\n"
        f"    with open({calc_path!r}) as f:\n"
        "        content = f.read()\n"
        "    assert not re.search(r'>=|<=', content)\n"
    )


def mutated_run_sleeps_past_timeout_body(calc_path: str) -> str:
    """Baseline passes quickly; a `>=`/`<=` mutant causes a sleep past the timeout."""
    return (
        "import re\n"
        "import time\n\n"
        "def test_qa():\n"
        f"    with open({calc_path!r}) as f:\n"
        "        content = f.read()\n"
        "    if re.search(r'>=|<=', content):\n"
        "        time.sleep(30)\n"
    )


def one_timeout_rest_killed_body(counter_path: str) -> str:
    """Baseline (call 0) passes; the first mutant (call 1) times out; the rest fail."""
    return (
        "import time\n\n"
        "def test_qa():\n"
        f"    counter_path = {counter_path!r}\n"
        "    with open(counter_path) as f:\n"
        "        count = int(f.read())\n"
        "    with open(counter_path, 'w') as f:\n"
        "        f.write(str(count + 1))\n"
        "    if count == 0:\n"  # baseline: always pass
        "        return\n"
        "    if count == 1:\n"  # first mutant: timeout
        "        time.sleep(30)\n"
        "        return\n"
        "    assert False\n"  # rest: killed
    )


def n_survivors_body(counter_path: str, n: int) -> str:
    """Baseline (call 0) passes; the first n mutant calls survive, the rest are killed."""
    return (
        "def test_qa():\n"
        f"    counter_path = {counter_path!r}\n"
        "    with open(counter_path) as f:\n"
        "        count = int(f.read())\n"
        "    with open(counter_path, 'w') as f:\n"
        "        f.write(str(count + 1))\n"
        "    if count == 0:\n"  # baseline: always pass
        "        return\n"
        f"    assert count <= {n}\n"  # first n mutant(s) survive; rest killed
    )


def all_killed_body(counter_path: str) -> str:
    """Baseline (call 0) passes; every mutant call is killed."""
    return (
        "def test_qa():\n"
        f"    counter_path = {counter_path!r}\n"
        "    with open(counter_path) as f:\n"
        "        count = int(f.read())\n"
        "    with open(counter_path, 'w') as f:\n"
        "        f.write(str(count + 1))\n"
        "    if count == 0:\n"  # baseline: always pass
        "        return\n"
        "    assert False\n"  # all mutants: killed
    )
