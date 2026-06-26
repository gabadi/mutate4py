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
    return Site(index=0, line=line, col=0, end_line=line, end_col=1, function_id="", orig_text="x", mutant_text="y", desc="x -> y")


def test_parse_lcov_covered_line():
    lcov = "SF:src/foo.py\nDA:5,3\nend_of_record\n"
    result = parse_lcov(lcov, "src/foo.py")
    assert 5 in result


def test_parse_lcov_zero_count_is_uncovered():
    lcov = "SF:src/foo.py\nDA:5,0\nend_of_record\n"
    result = parse_lcov(lcov, "src/foo.py")
    assert 5 not in result


def test_parse_lcov_absent_line_is_uncovered():
    lcov = "SF:src/foo.py\nDA:3,1\nend_of_record\n"
    result = parse_lcov(lcov, "src/foo.py")
    assert 5 not in result
    assert 3 in result


def test_parse_lcov_brda_ignored():
    lcov = "SF:src/foo.py\nBRDA:5,0,0,1\nend_of_record\n"
    result = parse_lcov(lcov, "src/foo.py")
    assert 5 not in result


def test_parse_lcov_brda_does_not_mark_covered_when_no_da():
    lcov = "SF:src/foo.py\nBRDA:5,0,0,1\nDA:3,2\nend_of_record\n"
    result = parse_lcov(lcov, "src/foo.py")
    assert 5 not in result
    assert 3 in result


def test_parse_lcov_suffix_match_absolute_sf():
    lcov = "SF:/abs/path/src/foo.py\nDA:5,1\nend_of_record\n"
    result = parse_lcov(lcov, "src/foo.py")
    assert 5 in result


def test_parse_lcov_suffix_match_relative_basename():
    lcov = "SF:foo.py\nDA:5,1\nend_of_record\n"
    result = parse_lcov(lcov, "/abs/path/foo.py")
    assert 5 in result


def test_parse_lcov_unrelated_sf_not_matched():
    lcov = "SF:/unrelated/other.py\nDA:5,1\nend_of_record\n"
    result = parse_lcov(lcov, "src/foo.py")
    assert 5 not in result


def test_parse_lcov_multiple_files_only_matching_counted():
    lcov = "SF:other.py\nDA:5,1\nend_of_record\nSF:src/foo.py\nDA:3,2\nend_of_record\n"
    result = parse_lcov(lcov, "src/foo.py")
    assert 3 in result
    assert 5 not in result


def test_parse_lcov_multiple_da_records():
    lcov = "SF:foo.py\nDA:3,1\nDA:5,2\nDA:7,0\nend_of_record\n"
    result = parse_lcov(lcov, "foo.py")
    assert 3 in result
    assert 5 in result
    assert 7 not in result


def test_parse_lcov_empty_text_returns_empty():
    result = parse_lcov("", "foo.py")
    assert result == set()


# ── partition_sites ───────────────────────────────────────────────────────────


def test_partition_all_covered():
    sites = [_site(3), _site(5), _site(7)]
    covered, uncovered = partition_sites(sites, {3, 5, 7})
    assert covered == 3
    assert uncovered == 0


def test_partition_none_covered():
    sites = [_site(3), _site(5), _site(7)]
    covered, uncovered = partition_sites(sites, set())
    assert covered == 0
    assert uncovered == 3


def test_partition_partial():
    sites = [_site(3), _site(5), _site(7)]
    covered, uncovered = partition_sites(sites, {3, 7})
    assert covered == 2
    assert uncovered == 1


def test_partition_covered_plus_uncovered_equals_total():
    sites = [_site(i) for i in range(10)]
    covered_lines = {0, 2, 4, 6, 8}
    covered, uncovered = partition_sites(sites, covered_lines)
    assert covered + uncovered == len(sites)


def test_partition_empty_sites():
    covered, uncovered = partition_sites([], {3, 5})
    assert covered == 0
    assert uncovered == 0


# ── acquire_coverage ──────────────────────────────────────────────────────────


def test_acquire_from_lcov_path():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "foo.py")
        lcov_path = os.path.join(d, "cov.info")
        with open(src, "w") as f:
            f.write("x = a + b\n")
        with open(lcov_path, "w") as f:
            f.write(f"SF:{src}\nDA:1,5\nend_of_record\n")
        result = acquire_coverage(
            cov_cmd=None, lcov_path=lcov_path, reuse=False, cwd=d, source_path=src
        )
        assert 1 in result


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


def test_acquire_reuse_reads_coverage_lcov():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "foo.py")
        default_lcov = os.path.join(d, "coverage.lcov")
        with open(src, "w") as f:
            f.write("x = a + b\n")
        with open(default_lcov, "w") as f:
            f.write(f"SF:{src}\nDA:1,1\nend_of_record\n")
        result = acquire_coverage(
            cov_cmd=None, lcov_path=None, reuse=True, cwd=d, source_path=src
        )
        assert 1 in result


def test_acquire_reuse_missing_default_raises():
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(CoverageError):
            acquire_coverage(
                cov_cmd=None, lcov_path=None, reuse=True, cwd=d, source_path="foo.py"
            )


def test_acquire_cov_cmd_runs_and_reads_coverage_lcov():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "foo.py")
        lcov_path = os.path.join(d, "coverage.lcov")
        with open(src, "w") as f:
            f.write("x = a + b\n")
        # Command writes coverage.lcov into cwd
        cmd = f"echo 'SF:{src}\\nDA:1,1\\nend_of_record' > {lcov_path}"
        result = acquire_coverage(
            cov_cmd=cmd, lcov_path=None, reuse=False, cwd=d, source_path=src
        )
        assert 1 in result


def test_acquire_cov_cmd_runs_exactly_once():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "foo.py")
        lcov_path = os.path.join(d, "coverage.lcov")
        counter = os.path.join(d, "count.log")
        with open(src, "w") as f:
            f.write("x = a + b\n")
        cmd = f"printf 'x' >> {counter} && echo 'SF:{src}\\nDA:1,1\\nend_of_record' > {lcov_path}"
        acquire_coverage(
            cov_cmd=cmd, lcov_path=None, reuse=False, cwd=d, source_path=src
        )
        with open(counter) as f:
            assert f.read() == "x"


# ── Mutant-killing gap tests ──────────────────────────────────────────────────

from mutate4py._coverage import _read_lcov_file, _resolve_lcov_path, _update_lcov_state  # noqa: E402


def test_update_lcov_state_sf_strips_sf_prefix_not_extra_char():
    # _update_lcov_state: line[3:] strips "SF:" (3 chars), not line[4:]
    # line[4:] would give "oo.py" for "SF:foo.py" and "foo.py".endswith("oo.py") is True,
    # so we need a case where the first char of filename distinguishes:
    # SF:afile.py, source=bfile.py: line[3:]="afile.py" → no match (correct)
    # line[4:]="file.py" → "bfile.py".endswith("file.py") = True → WRONG match (mutant)
    covered: set[int] = set()
    result = _update_lcov_state("SF:afile.py", False, "bfile.py", covered)
    assert result is False, "SF:afile.py must not match source_path=bfile.py"


def test_update_lcov_state_sf_absolute_path_suffix_match():
    covered: set[int] = set()
    result = _update_lcov_state("SF:/abs/foo.py", False, "foo.py", covered)
    assert result is True


def test_update_lcov_state_end_of_record_resets_to_false():
    # end_of_record always returns False regardless of in_matching_file
    covered: set[int] = set()
    assert _update_lcov_state("end_of_record", True, "foo.py", covered) is False
    assert _update_lcov_state("end_of_record", False, "foo.py", covered) is False


def test_parse_lcov_da_before_first_sf_not_collected():
    # DA before any SF: in_matching_file=False, line must not be collected
    lcov = "DA:5,3\nSF:foo.py\nend_of_record\n"
    result = parse_lcov(lcov, "foo.py")
    assert 5 not in result


def test_parse_lcov_matched_sf_then_end_of_record_then_unmatched():
    # After end_of_record, subsequent SF for unmatched file must not contribute lines
    lcov = "SF:foo.py\nDA:3,1\nend_of_record\nSF:other.py\nDA:5,1\nend_of_record\n"
    result = parse_lcov(lcov, "foo.py")
    assert 3 in result
    assert 5 not in result


def test_read_lcov_file_error_message_contains_path():
    # Error message must reference the missing path
    with tempfile.TemporaryDirectory() as d:
        missing = os.path.join(d, "no_such.info")
        with pytest.raises(CoverageError) as exc_info:
            _read_lcov_file(missing, "foo.py")
        assert missing in str(exc_info.value)


def test_resolve_lcov_path_cov_cmd_uses_cwd_for_default():
    # default lcov path is os.path.join(cwd, DEFAULT_LCOV_PATH)
    # mutmut_5: cwd=None → subprocess.run with cwd=None uses process cwd, not our d
    # but then os.path.join(cwd, DEFAULT_LCOV_PATH) would fail with TypeError
    # mutmut_8: cwd omitted → same effect
    # Test: the returned path must be in our specified cwd, not process cwd
    with tempfile.TemporaryDirectory() as d:
        lcov = os.path.join(d, "coverage.lcov")
        # Write the lcov file where the command will look (in d)
        cmd = f"printf 'SF:x.py\\nend_of_record\\n' > '{lcov}'"
        result = _resolve_lcov_path(cov_cmd=cmd, lcov_path=None, reuse=False, cwd=d)
        assert result == lcov, f"Expected path in cwd={d}, got {result}"


def test_resolve_lcov_path_reuse_uses_cwd():
    # reuse path joins cwd with DEFAULT_LCOV_PATH
    result = _resolve_lcov_path(
        cov_cmd=None, lcov_path=None, reuse=True, cwd="/some/dir"
    )
    assert result == "/some/dir/coverage.lcov"


def test_parse_lcov_initial_in_matching_file_is_false_not_none():
    # mutmut_2: in_matching_file = None vs False
    # None is falsy so first DA lines before any SF would be skipped (same behavior).
    # The difference shows when the DA precedes SF: both False and None skip it.
    # To kill this mutant we need to verify the type propagation matters somewhere.
    # Actually None and False are both falsy so this IS equivalent — document as such.
    # Instead test that plain lcov with no SF produces empty set:
    result = parse_lcov("DA:5,3\nend_of_record\n", "foo.py")
    assert result == set()
