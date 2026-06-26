"""Unit tests for mutate4py._coverage (TDD — written before implementation)."""
import os
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mutate4py._coverage import CoverageError, acquire_coverage, parse_lcov
from mutate4py._discovery import Site, partition_sites


# ── parse_lcov ────────────────────────────────────────────────────────────────

def _site(line: int) -> Site:
    return Site(index=0, line=line, col=0, function_id="")


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
    lcov = (
        "SF:other.py\nDA:5,1\nend_of_record\n"
        "SF:src/foo.py\nDA:3,2\nend_of_record\n"
    )
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
        result = acquire_coverage(cov_cmd=None, lcov_path=lcov_path, reuse=False, cwd=d, source_path=src)
        assert 1 in result


def test_acquire_missing_lcov_path_raises():
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(CoverageError):
            acquire_coverage(cov_cmd=None, lcov_path=os.path.join(d, "missing.info"), reuse=False, cwd=d, source_path="foo.py")


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


def test_acquire_reuse_missing_default_raises():
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(CoverageError):
            acquire_coverage(cov_cmd=None, lcov_path=None, reuse=True, cwd=d, source_path="foo.py")


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
