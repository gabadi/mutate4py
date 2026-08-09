"""Wires the module size guard into the existing test gate (issue #38).

Caps were chosen from the measured line/def distribution at the time this
gate was written, picked at the widest gap in each distribution so the
exempt set stays small and clearly separated from everything else:

  src/mutate4py/*.py           : the next-largest file after the two
                                  exempt outliers is 323 lines / 19 defs,
                                  well under the 400/25 cap.
  tests/*.py, acceptance/steps/*.py : the next-largest file after the two
                                  exempt outliers is 695 lines / 78 defs,
                                  well under the 1000/100 cap.

Re-run the measurement (see `_module_size_guard.measure`) before changing
either the caps or the exemption table below.
"""

from pathlib import Path

from ._module_size_guard import Caps, ExemptionEntry, check_file, check_files

REPO_ROOT = Path(__file__).resolve().parent.parent

SRC_CAPS = Caps(max_lines=400, max_defs=25)
TEST_CAPS = Caps(max_lines=1000, max_defs=100)

EXEMPTIONS = {
    "src/mutate4py/_runner.py": ExemptionEntry(lines=575, defs=28),
    "tests/test_main.py": ExemptionEntry(lines=1700, defs=138),
    "tests/test_runner.py": ExemptionEntry(lines=1681, defs=97),
}


def _py_files(directory: Path) -> dict[str, Path]:
    return {p.relative_to(REPO_ROOT).as_posix(): p for p in sorted(directory.glob("*.py"))}


def test_no_module_exceeds_its_size_cap_or_exemption_entry():
    violations = check_files(_py_files(REPO_ROOT / "src" / "mutate4py"), SRC_CAPS, EXEMPTIONS)
    for test_dir in (REPO_ROOT / "tests", REPO_ROOT / "acceptance" / "steps"):
        violations += check_files(_py_files(test_dir), TEST_CAPS, EXEMPTIONS)

    assert not violations, "Module size guard violations:\n" + "\n".join(f"  {v}" for v in violations)


# --- Guard unit tests (issue #38 AC) ---------------------------------------

_CAPS = Caps(max_lines=10, max_defs=3)


def _write_module(path: Path, *, lines: int, defs: int) -> None:
    body = [f"def f{i}(): pass" for i in range(defs)]
    while len(body) < lines:
        body.append("# padding")
    path.write_text("\n".join(body) + "\n")


def test_file_over_cap_without_entry_fails(tmp_path):
    path = tmp_path / "mod.py"
    _write_module(path, lines=11, defs=1)

    violation = check_file("mod.py", path, _CAPS, {})

    assert violation is not None
    assert "mod.py" in violation
    assert "no exemption entry" in violation


def test_file_over_its_exemption_entry_fails(tmp_path):
    path = tmp_path / "mod.py"
    _write_module(path, lines=16, defs=1)
    exemptions = {"mod.py": ExemptionEntry(lines=15, defs=1)}

    violation = check_file("mod.py", path, _CAPS, exemptions)

    assert violation is not None
    assert "exceeds its exemption entry" in violation


def test_file_under_its_exemption_entry_fails(tmp_path):
    path = tmp_path / "mod.py"
    _write_module(path, lines=12, defs=1)
    exemptions = {"mod.py": ExemptionEntry(lines=15, defs=1)}

    violation = check_file("mod.py", path, _CAPS, exemptions)

    assert violation is not None
    assert "is below its exemption entry" in violation
    assert "lines=12" in violation


def test_exempt_file_exactly_at_its_entry_passes(tmp_path):
    path = tmp_path / "mod.py"
    _write_module(path, lines=15, defs=1)
    exemptions = {"mod.py": ExemptionEntry(lines=15, defs=1)}

    violation = check_file("mod.py", path, _CAPS, exemptions)

    assert violation is None


def test_new_file_over_cap_fails(tmp_path):
    # Not in the exemption table at all — a freshly written file, over cap
    # on the definitions axis rather than the lines axis.
    path = tmp_path / "brand_new.py"
    _write_module(path, lines=8, defs=4)

    violation = check_file("brand_new.py", path, _CAPS, {})

    assert violation is not None
    assert "brand_new.py" in violation
    assert "defs=4" in violation


def test_check_files_aggregates_every_offending_file(tmp_path):
    good = tmp_path / "good.py"
    _write_module(good, lines=5, defs=1)
    bad_one = tmp_path / "bad_one.py"
    _write_module(bad_one, lines=11, defs=1)
    bad_two = tmp_path / "bad_two.py"
    _write_module(bad_two, lines=5, defs=4)

    violations = check_files(
        {"good.py": good, "bad_one.py": bad_one, "bad_two.py": bad_two},
        _CAPS,
        {},
    )

    assert len(violations) == 2
    assert any("bad_one.py" in v for v in violations)
    assert any("bad_two.py" in v for v in violations)
