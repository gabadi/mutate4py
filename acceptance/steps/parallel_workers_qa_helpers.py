"""Pure helpers for features/parallel-workers_qa.feature's step handlers.

Extracted from parallel_workers_qa_steps.py so the fake-pytest-test source
bodies (string construction from parameters, no ctx/subprocess coupling) have
their own unit tests, per this repo's boundary-file convention for
acceptance step files.
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


def counted_all_killed_body(counter_path: str) -> str:
    """Call 0 (the baseline, always serial and first) passes; every later
    call (a mutant, possibly racing other workers) fails."""
    return (
        "def test_qa():\n"
        f"    counter_path = {counter_path!r}\n"
        "    with open(counter_path) as f:\n"
        "        count = int(f.read())\n"
        "    with open(counter_path, 'w') as f:\n"
        "        f.write(str(count + 1))\n"
        "    if count == 0:\n"
        "        return\n"
        "    assert False\n"
    )


def sleep_past_timeout_body(counter_path: str) -> str:
    """Baseline (call 0) passes quickly; every mutant call sleeps past the timeout."""
    return (
        "import time\n\n"
        "def test_qa():\n"
        f"    counter_path = {counter_path!r}\n"
        "    with open(counter_path) as f:\n"
        "        count = int(f.read())\n"
        "    with open(counter_path, 'w') as f:\n"
        "        f.write(str(count + 1))\n"
        "    if count == 0:\n"
        "        return\n"
        "    time.sleep(30)\n"
    )


def single_survivor_body(baseline_done: str, src_rel: str) -> str:
    """Baseline passes; a mutant call survives only if the worker copy still
    carries calc1's `a >= b` mutant (calc.py's other three sites are killed)."""
    return (
        "import os\n\n"
        "def test_qa():\n"
        f"    baseline_done = {baseline_done!r}\n"
        "    if not os.path.exists(baseline_done):\n"
        "        open(baseline_done, 'w').close()\n"
        "        return\n"
        f"    with open({src_rel!r}) as f:\n"
        "        content = f.read()\n"
        "    assert 'a >= b' in content\n"
    )


def record_cwd_and_kill_body(baseline_done: str, sentinels_dir: str) -> str:
    """Baseline passes; every mutant call records its cwd to a sentinel file, then fails."""
    return (
        "import os\n\n"
        "def test_qa():\n"
        f"    baseline_done = {baseline_done!r}\n"
        "    if not os.path.exists(baseline_done):\n"
        "        open(baseline_done, 'w').close()\n"
        "        return\n"
        f"    sentinels_dir = {sentinels_dir!r}\n"
        "    with open(os.path.join(sentinels_dir, f'wd_{os.getpid()}.txt'), 'w') as f:\n"
        "        f.write(os.getcwd())\n"
        "    assert False\n"
    )


def check_worker_tree_body(baseline_done: str, first_mutant_done: str, sentinel: str) -> str:
    """Baseline passes; the first mutant call checks whether its cwd is under a
    `.mutate4py/workers/` tree and records that observation to a sentinel, then fails."""
    return (
        "import os\n\n"
        "def test_qa():\n"
        f"    baseline_done = {baseline_done!r}\n"
        "    if not os.path.exists(baseline_done):\n"
        "        open(baseline_done, 'w').close()\n"
        "        return\n"
        f"    first_mutant_done = {first_mutant_done!r}\n"
        "    if not os.path.exists(first_mutant_done):\n"
        "        open(first_mutant_done, 'w').close()\n"
        "        if os.sep.join(['.mutate4py', 'workers']) in os.getcwd():\n"
        f"            with open({sentinel!r}, 'w') as f:\n"
        "                f.write('observed')\n"
        "    assert False\n"
    )
