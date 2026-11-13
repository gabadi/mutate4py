"""Pure helpers for the parallel-workers acceptance steps.

A scenario observes where the project's tests really run: a probe line at the top of
every test appends the working directory, whether the worker tree exists, and whether
the original source holds a Mutant. The Measurement runs every test once, in the
original directory, before any worker exists: those are the first `tests` records;
the rest are mutated runs.
Unit tests: tests/test_parallel_workers_helpers.py.
"""

import os
import re
from dataclasses import dataclass

WORKERS_RELATIVE = os.path.join(".mutate4py", "workers")

_MUTANT_MARK = ">="


@dataclass(frozen=True)
class Placement:
    cwd: str
    worker_tree_exists: bool
    original_spliced: bool


def placement_probe(record_path: str, workers_dir: str, source_path: str) -> str:
    """One statement for the top of a test: append `cwd|worker tree exists|original spliced` to `record_path`."""
    os_ = '__import__("os")'
    fields = (
        f"{os_}.getcwd()",
        f"str({os_}.path.isdir({workers_dir!r}))",
        f"str({_MUTANT_MARK!r} in open({source_path!r}).read())",
    )
    return f'open({record_path!r}, "a").write("|".join([{", ".join(fields)}]) + "\\n")'


def parse_placements(text: str) -> list[Placement]:
    placements = []
    for line in text.splitlines():
        cwd, tree, spliced = line.split("|")
        placements.append(Placement(cwd, tree == "True", spliced == "True"))
    return placements


def read_placements(record_path: str) -> list[Placement]:
    assert os.path.exists(record_path), f"no test recorded where it ran: {record_path} is missing"
    with open(record_path) as f:
        placements = parse_placements(f.read())
    assert placements, f"{record_path} holds no records"
    return placements


def _inside(path: str, directory: str) -> bool:
    return os.path.realpath(path).startswith(os.path.realpath(directory) + os.sep)


def assert_measured_in_original(placements: list[Placement], project_dir: str, tests: int) -> None:
    measured = placements[:tests]
    assert len(measured) == tests, f"the Measurement recorded {len(measured)} of {tests} tests"
    elsewhere = [p.cwd for p in measured if os.path.realpath(p.cwd) != os.path.realpath(project_dir)]
    assert not elsewhere, f"the Measurement should run in {project_dir}, ran in {elsewhere}"
    assert not any(p.worker_tree_exists for p in measured), "a worker tree existed before the Measurement ran"


def assert_mutants_ran_in_workers(placements: list[Placement], project_dir: str, tests: int) -> None:
    mutated = placements[tests:]
    assert mutated, "no mutated test run was recorded after the Measurement"
    workers_dir = os.path.join(project_dir, WORKERS_RELATIVE)
    outside = [p.cwd for p in mutated if not _inside(p.cwd, workers_dir)]
    assert not outside, f"mutated runs outside {workers_dir}: {outside}"


def assert_worker_tree_seen_during_run(placements: list[Placement], tests: int) -> None:
    mutated = placements[tests:]
    assert mutated, "no mutated test run was recorded after the Measurement"
    assert all(p.worker_tree_exists for p in mutated), "a mutated run saw no worker tree under .mutate4py/workers/"


def assert_original_never_spliced(placements: list[Placement]) -> None:
    spliced = [p.cwd for p in placements if p.original_spliced]
    assert not spliced, f"the original source held a Mutant while tests ran in: {spliced}"


def report_tally(stdout: str, label: str) -> int:
    """The count on a report line such as `Killed: 3`."""
    match = re.search(rf"^{re.escape(label)}: (\d+)$", stdout, re.MULTILINE)
    assert match, f"no {label!r} line in the report:\n{stdout}"
    return int(match.group(1))


def survivor_lines(stdout: str) -> list[str]:
    """The site lines under the `Survivors:` block of a report, in print order."""
    lines = stdout.splitlines()
    if "Survivors:" not in lines:
        return []
    block = []
    for line in lines[lines.index("Survivors:") + 1 :]:
        if not line.startswith("  "):
            break
        block.append(line.strip())
    return block
