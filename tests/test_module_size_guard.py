"""Wires the module size guard into the existing test gate (issue #38).

Caps were chosen from the measured line/def distribution at the time this
gate was written, picked at the widest gap in each distribution so the
outliers this gate exists to catch stay clearly separated from everything
else:

  src/mutate4py/*.py           : the next-largest file after the two
                                  original outliers is 323 lines / 19 defs,
                                  well under the 400/25 cap.
  tests/*.py, acceptance/steps/*.py : the next-largest file after the two
                                  original outliers is 695 lines / 78 defs,
                                  well under the 1000/100 cap.

Re-run the measurement (see `_module_size_guard.measure`) before changing
the caps. There is no per-file exemption: every file must independently
fit under its flat cap (issue #38 gate 07 — an earlier per-file exemption
ratchet was removed because it let files grow past the caps it was meant
to enforce).
"""

from pathlib import Path

from ._module_size_guard import Caps, check_file, check_files
import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent

SRC_CAPS = Caps(max_lines=400, max_defs=25)
TEST_CAPS = Caps(max_lines=1000, max_defs=100)


def _py_files(directory: Path) -> dict[str, Path]:
    return {p.relative_to(REPO_ROOT).as_posix(): p for p in sorted(directory.glob("*.py"))}


@pytest.mark.unit
def test_no_module_exceeds_its_size_cap():
    violations = check_files(_py_files(REPO_ROOT / "src" / "mutate4py"), SRC_CAPS)
    for test_dir in (REPO_ROOT / "tests", REPO_ROOT / "acceptance" / "steps"):
        violations += check_files(_py_files(test_dir), TEST_CAPS)

    assert not violations, "Module size guard violations:\n" + "\n".join(f"  {v}" for v in violations)


# --- Guard unit tests (issue #38 AC) ---------------------------------------

_CAPS = Caps(max_lines=10, max_defs=3)


def _write_module(path: Path, *, lines: int, defs: int) -> None:
    body = [f"def f{i}(): pass" for i in range(defs)]
    while len(body) < lines:
        body.append("# padding")
    path.write_text("\n".join(body) + "\n")


@pytest.mark.unit
def test_file_over_cap_on_lines_fails(tmp_path):
    path = tmp_path / "mod.py"
    _write_module(path, lines=11, defs=1)

    violation = check_file("mod.py", path, _CAPS)

    assert violation is not None
    assert "mod.py" in violation
    assert "lines=11" in violation


@pytest.mark.unit
def test_file_over_cap_on_defs_fails(tmp_path):
    path = tmp_path / "mod.py"
    _write_module(path, lines=8, defs=4)

    violation = check_file("mod.py", path, _CAPS)

    assert violation is not None
    assert "mod.py" in violation
    assert "defs=4" in violation


@pytest.mark.unit
def test_file_under_cap_passes(tmp_path):
    path = tmp_path / "mod.py"
    _write_module(path, lines=5, defs=1)

    violation = check_file("mod.py", path, _CAPS)

    assert violation is None


@pytest.mark.unit
def test_file_exactly_at_cap_passes(tmp_path):
    path = tmp_path / "mod.py"
    _write_module(path, lines=10, defs=3)

    violation = check_file("mod.py", path, _CAPS)

    assert violation is None


@pytest.mark.unit
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
    )

    assert len(violations) == 2
    assert any("bad_one.py" in v for v in violations)
    assert any("bad_two.py" in v for v in violations)
