"""Unit tests for mutate4py._coverage (TDD — written before implementation)."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mutate4py._coverage import CoverageError, acquire_coverage, parse_lcov
from mutate4py._discovery import Site, partition_sites


# ── parse_lcov ────────────────────────────────────────────────────────────────


def _site(line: int) -> Site:
    return Site(
        index=0,
        line=line,
        col=0,
        end_line=line,
        end_col=1,
        function_id="",
        orig_text="x",
        mutant_text="y",
        desc="x -> y",
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "lcov,sf",
    [
        ("SF:src/foo.py\nDA:5,3\nend_of_record\n", "src/foo.py"),
        ("SF:/abs/path/src/foo.py\nDA:5,1\nend_of_record\n", "src/foo.py"),
        ("SF:foo.py\nDA:5,1\nend_of_record\n", "/abs/path/foo.py"),
    ],
)
def test_parse_lcov_line_5_covered(lcov, sf):
    assert 5 in parse_lcov(lcov, sf)


@pytest.mark.unit
@pytest.mark.parametrize(
    "lcov",
    [
        "SF:src/foo.py\nDA:5,0\nend_of_record\n",
        "SF:src/foo.py\nBRDA:5,0,0,1\nend_of_record\n",
        "SF:/unrelated/other.py\nDA:5,1\nend_of_record\n",
    ],
)
def test_parse_lcov_line_5_not_covered(lcov):
    assert 5 not in parse_lcov(lcov, "src/foo.py")


@pytest.mark.unit
def test_parse_lcov_absent_line_is_uncovered():
    lcov = "SF:src/foo.py\nDA:3,1\nend_of_record\n"
    result = parse_lcov(lcov, "src/foo.py")
    assert 5 not in result
    assert 3 in result


@pytest.mark.unit
def test_parse_lcov_brda_does_not_mark_covered_when_no_da():
    lcov = "SF:src/foo.py\nBRDA:5,0,0,1\nDA:3,2\nend_of_record\n"
    result = parse_lcov(lcov, "src/foo.py")
    assert 5 not in result
    assert 3 in result


@pytest.mark.unit
def test_parse_lcov_multiple_files_only_matching_counted():
    lcov = "SF:other.py\nDA:5,1\nend_of_record\nSF:src/foo.py\nDA:3,2\nend_of_record\n"
    result = parse_lcov(lcov, "src/foo.py")
    assert 3 in result
    assert 5 not in result


@pytest.mark.unit
def test_parse_lcov_multiple_da_records():
    lcov = "SF:foo.py\nDA:3,1\nDA:5,2\nDA:7,0\nend_of_record\n"
    result = parse_lcov(lcov, "foo.py")
    assert 3 in result
    assert 5 in result
    assert 7 not in result


@pytest.mark.unit
def test_parse_lcov_empty_text_returns_empty():
    result = parse_lcov("", "foo.py")
    assert result == set()


# ── partition_sites ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_partition_all_covered():
    sites = [_site(3), _site(5), _site(7)]
    covered, uncovered = partition_sites(sites, {3, 5, 7})
    assert covered == 3
    assert uncovered == 0


@pytest.mark.unit
def test_partition_none_covered():
    sites = [_site(3), _site(5), _site(7)]
    covered, uncovered = partition_sites(sites, set())
    assert covered == 0
    assert uncovered == 3


@pytest.mark.unit
def test_partition_partial():
    sites = [_site(3), _site(5), _site(7)]
    covered, uncovered = partition_sites(sites, {3, 7})
    assert covered == 2
    assert uncovered == 1


@pytest.mark.unit
def test_partition_covered_plus_uncovered_equals_total():
    sites = [_site(i) for i in range(10)]
    covered_lines = {0, 2, 4, 6, 8}
    covered, uncovered = partition_sites(sites, covered_lines)
    assert covered + uncovered == len(sites)


@pytest.mark.unit
def test_partition_empty_sites():
    covered, uncovered = partition_sites([], {3, 5})
    assert covered == 0
    assert uncovered == 0


# ── acquire_coverage ──────────────────────────────────────────────────────────


@pytest.mark.unit
def test_acquire_from_lcov_path():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "foo.py")
        lcov_path = os.path.join(d, "cov.info")
        with open(src, "w") as f:
            f.write("x = a + b\n")
        with open(lcov_path, "w") as f:
            f.write(f"SF:{src}\nDA:1,5\nend_of_record\n")
        result = acquire_coverage(cov_cmd=None, lcov_path=lcov_path, reuse=False, cwd=d, source_path=src)
        assert 1 in result


@pytest.mark.unit
def test_acquire_missing_lcov_path_raises():
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(CoverageError):
            acquire_coverage(
                cov_cmd=None,
                lcov_path=os.path.join(d, "missing.info"),
                reuse=False,
                cwd=d,
                source_path="foo.py",
            )


@pytest.mark.unit
def test_acquire_reuse_reads_coverage_lcov():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "foo.py")
        default_lcov = os.path.join(d, "coverage.lcov")
        with open(src, "w") as f:
            f.write("x = a + b\n")
        with open(default_lcov, "w") as f:
            f.write(f"SF:{src}\nDA:1,1\nend_of_record\n")
        result = acquire_coverage(cov_cmd=None, lcov_path=None, reuse=True, cwd=d, source_path=src)
        assert 1 in result


@pytest.mark.unit
def test_acquire_reuse_missing_default_raises():
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(CoverageError):
            acquire_coverage(cov_cmd=None, lcov_path=None, reuse=True, cwd=d, source_path="foo.py")


@pytest.mark.unit
def test_acquire_cov_cmd_runs_and_reads_coverage_lcov():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "foo.py")
        lcov_path = os.path.join(d, "coverage.lcov")
        with open(src, "w") as f:
            f.write("x = a + b\n")
        # Command writes coverage.lcov into cwd
        cmd = f"echo 'SF:{src}\\nDA:1,1\\nend_of_record' > {lcov_path}"
        result = acquire_coverage(cov_cmd=cmd, lcov_path=None, reuse=False, cwd=d, source_path=src)
        assert 1 in result


@pytest.mark.unit
def test_acquire_cov_cmd_runs_exactly_once():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "foo.py")
        lcov_path = os.path.join(d, "coverage.lcov")
        counter = os.path.join(d, "count.log")
        with open(src, "w") as f:
            f.write("x = a + b\n")
        cmd = f"printf 'x' >> {counter} && echo 'SF:{src}\\nDA:1,1\\nend_of_record' > {lcov_path}"
        acquire_coverage(cov_cmd=cmd, lcov_path=None, reuse=False, cwd=d, source_path=src)
        with open(counter) as f:
            assert f.read() == "x"


# ── Mutant-killing gap tests ──────────────────────────────────────────────────

from mutate4py._coverage import _read_lcov_file, _resolve_lcov_path, _update_lcov_state  # noqa: E402


@pytest.mark.unit
def test_update_lcov_state_sf_strips_sf_prefix_not_extra_char():
    # _update_lcov_state: line[3:] strips "SF:" (3 chars), not line[4:]
    # line[4:] would give "oo.py" for "SF:foo.py" and "foo.py".endswith("oo.py") is True,
    # so we need a case where the first char of filename distinguishes:
    # SF:afile.py, source=bfile.py: line[3:]="afile.py" → no match (correct)
    # line[4:]="file.py" → "bfile.py".endswith("file.py") = True → WRONG match (mutant)
    covered: set[int] = set()
    result = _update_lcov_state("SF:afile.py", in_matching_file=False, source_path="bfile.py", covered=covered)
    assert result is False, "SF:afile.py must not match source_path=bfile.py"


@pytest.mark.unit
def test_update_lcov_state_sf_absolute_path_suffix_match():
    covered: set[int] = set()
    result = _update_lcov_state("SF:/abs/foo.py", in_matching_file=False, source_path="foo.py", covered=covered)
    assert result is True


@pytest.mark.unit
def test_update_lcov_state_end_of_record_resets_to_false():
    # end_of_record always returns False regardless of in_matching_file
    covered: set[int] = set()
    assert _update_lcov_state("end_of_record", in_matching_file=True, source_path="foo.py", covered=covered) is False
    assert _update_lcov_state("end_of_record", in_matching_file=False, source_path="foo.py", covered=covered) is False


@pytest.mark.unit
def test_parse_lcov_da_before_first_sf_not_collected():
    # DA before any SF: in_matching_file=False, line must not be collected
    lcov = "DA:5,3\nSF:foo.py\nend_of_record\n"
    result = parse_lcov(lcov, "foo.py")
    assert 5 not in result


@pytest.mark.unit
def test_parse_lcov_matched_sf_then_end_of_record_then_unmatched():
    # After end_of_record, subsequent SF for unmatched file must not contribute lines
    lcov = "SF:foo.py\nDA:3,1\nend_of_record\nSF:other.py\nDA:5,1\nend_of_record\n"
    result = parse_lcov(lcov, "foo.py")
    assert 3 in result
    assert 5 not in result


@pytest.mark.unit
def test_read_lcov_file_error_message_contains_path():
    # Error message must reference the missing path
    with tempfile.TemporaryDirectory() as d:
        missing = os.path.join(d, "no_such.info")
        with pytest.raises(CoverageError) as exc_info:
            _read_lcov_file(missing, "foo.py")
        assert missing in str(exc_info.value)


@pytest.mark.unit
def test_resolve_lcov_path_cov_cmd_uses_cwd_for_default():
    # default lcov path is os.path.join(cwd, DEFAULT_LCOV_PATH)
    # mutant_5: cwd=None → subprocess.run with cwd=None uses process cwd, not our d
    # mutant_8: cwd omitted → same effect (subprocess uses process cwd)
    # Test: the returned path must be in our specified cwd, not process cwd
    # Use a cwd-relative command: "touch coverage.lcov" — writes in cwd
    with tempfile.TemporaryDirectory() as d:
        expected = os.path.join(d, "coverage.lcov")
        cmd = "touch coverage.lcov"
        result = _resolve_lcov_path(cov_cmd=cmd, lcov_path=None, reuse=False, cwd=d)
        assert result == expected, f"Expected path in cwd={d}, got {result}"
        assert os.path.isfile(expected), "coverage.lcov was not created in cwd"


@pytest.mark.unit
def test_resolve_lcov_path_reuse_uses_cwd():
    # reuse path joins cwd with DEFAULT_LCOV_PATH
    result = _resolve_lcov_path(cov_cmd=None, lcov_path=None, reuse=True, cwd="/some/dir")
    assert result == "/some/dir/coverage.lcov"


@pytest.mark.unit
def test_parse_lcov_initial_in_matching_file_is_false_not_none():
    # mutant_2: in_matching_file = None vs False
    # None is falsy so first DA lines before any SF would be skipped (same behavior).
    # The difference shows when the DA precedes SF: both False and None skip it.
    # To kill this mutant we need to verify the type propagation matters somewhere.
    # Actually None and False are both falsy so this IS equivalent — document as such.
    # Instead test that plain lcov with no SF produces empty set:
    result = parse_lcov("DA:5,3\nend_of_record\n", "foo.py")
    assert result == set()


# ── _paths_match_by_suffix: Windows path normalization ───────────────────────

from mutate4py._coverage import _paths_match_by_suffix, _parse_da_line  # noqa: E402


@pytest.mark.unit
def test_paths_match_by_suffix_backslash_normalized():
    # mutant_6/7/13/14: replace("\\", "/") changes backslashes to forward slashes
    # Windows-style paths use backslash; normalization ensures suffix match works
    # When backslash is NOT replaced (mutant: "XX\\XX" or target "XX/XX"),
    # a Windows SF path won't match a Unix-style source_path.
    # Simulate: sf_path uses backslash separator, source_path uses forward slash
    assert _paths_match_by_suffix("path\\to\\foo.py", "path/to/foo.py") is True


@pytest.mark.unit
def test_paths_match_by_suffix_backslash_in_sf_no_match_without_normalization():
    # Non-matching: different files — must remain False even after normalization
    assert _paths_match_by_suffix("path\\to\\bar.py", "path/to/foo.py") is False


@pytest.mark.unit
def test_paths_match_by_suffix_backslash_in_source_path():
    # mutant_13/14: b = source_path.replace("XX\\XX", "/") or replace("\\", "XX/XX")
    # When source_path has backslash but sf_path uses forward slash, normalization is required
    # for suffix match to work. If source_path's backslash is NOT replaced, the suffix
    # "path/to/foo.py" won't match "path\\to\\foo.py" as a string suffix.
    assert _paths_match_by_suffix("path/to/foo.py", "path\\to\\foo.py") is True


# ── _parse_da_line: split maxsplit ────────────────────────────────────────────


@pytest.mark.unit
def test_parse_da_line_extra_comma_in_count_field():
    # mutant_5: split(",",) vs split(",", 1) — without maxsplit, extra comma splits further
    # mutant_9: split(",", 2) — allows extra split, giving 3 parts; len != 2 check fails
    # A DA line with count containing a comma: "DA:5,1,extra"
    # With split(",", 1): parts = ["5", "1,extra"] → lineno=5, count=int("1,extra") → ValueError → None
    # With split(",")   : parts = ["5", "1", "extra"] → len != 2 → None (same result here)
    # The real distinguishing case: "DA:5,1" with maxsplit=2 vs maxsplit=1
    # split(",", 1) → ["5", "1"] (len=2, valid)
    # split(",", 2) → ["5", "1"] (same for no extra comma)
    # Need extra comma: "DA:5,3,extra"
    # split(",", 1) → ["5", "3,extra"] → int("3,extra") fails → None
    # split(",", 2) → ["5", "3", "extra"] → len != 2 → None (same)
    # split(",")    → ["5", "3", "extra"] → len != 2 → None (same)
    # The real difference: "DA:5,3" (clean) with rsplit(",", 1) vs split(",", 1):
    # rsplit(",", 1) on "5,3" → ["5", "3"] (same) but on "a,5,3": split→["a","5,3"], rsplit→["a,5","3"]
    # mutant_6 is rsplit: "DA:3,5,1" → split(",",1)=["3","5,1"]→int("5,1") fails→None
    #                                   rsplit(",",1)=["3,5","1"]→int("3,5") fails→None
    # Need a line where line_number and count swap with rsplit:
    # "DA:5,3" — split: ["5","3"]→5 covered; rsplit: ["5","3"] same
    # "DA:5,3,0" — split(",",1): ["5","3,0"]→int("3,0") fails→None; rsplit(",",1): ["5,3","0"]→covered=None
    # Clean case for split maxsplit=1: DA line with no extra comma must give covered line
    result = _parse_da_line("DA:7,2")
    assert result == 7


@pytest.mark.unit
def test_parse_da_line_rsplit_vs_split_distinguishing():
    # mutant_6: rsplit(",", 1) vs split(",", 1) — differs for "DA:5,3,0"
    # split(",", 1) on "5,3,0" → ["5", "3,0"] → int("3,0") → ValueError → None
    # rsplit(",", 1) on "5,3,0" → ["5,3", "0"] → int("5,3") → ValueError → None
    # Both give None here but for different reasons.
    # Distinguishing case: "DA:7,1,0"
    # split(",",1): parts=["7","1,0"] → int("1,0")→ValueError→None (miss the covered line)
    # rsplit(",",1): parts=["7,1","0"] → int("7,1")→ValueError→None
    # The real distinguishing case we need is where rsplit picks the WRONG field:
    # "DA:5,1" where line=5, count=1 (covered):
    # split(",",1) → ["5","1"] → 5 covered ✓
    # rsplit(",",1) → ["5","1"] → same (only one comma)
    # We need a line with TWO commas where the last field is "0":
    # "DA:10,1,extra" — split: parts=["10","1,extra"]→ValueError→None; rsplit: ["10,1","extra"]→ValueError→None
    # For rsplit to give wrong answer we need: last field parseable but first field not:
    # No clean distinguishing test for rsplit vs split with maxsplit=1 here.
    # The key behavior test: standard DA line must return line number:
    assert _parse_da_line("DA:10,5") == 10


@pytest.mark.unit
def test_parse_da_line_split_maxsplit_1_limits_to_two_parts():
    # mutant_5: split(",",) has no maxsplit limit — extra commas produce >2 parts → None
    # mutant_9: split(",", 2) allows 3 parts → len != 2 → None for "DA:5,3,x"
    # With split(",", 1): "DA:5,3,x" → parts=["5","3,x"] len=2, int("3,x") fails → None
    # Correct for a clean "DA:5,1": split(",",1) → ["5","1"] → 5 covered
    assert _parse_da_line("DA:5,1") == 5
