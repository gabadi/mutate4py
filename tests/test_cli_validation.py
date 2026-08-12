"""Unit tests for mutate4py._cli_validation (issue #38 gate 12).

Assert on raised errors, not process exit and captured stderr — this module
never calls sys.exit or print (that's the CLI adapter's job; see
tests/test_main.py for adapter-level coverage of exit codes and stderr
text, via subprocess CLI invocations and in-process main()/argv tests).
"""

import argparse

import pytest

from mutate4py._cli_validation import (
    ValidationError,
    _check_coverage_flags,
    _check_no_run_incompatibilities,
    _validate_mutual_exclusions,
)


def _make_args(**kwargs):
    """Build a minimal argparse.Namespace for validation tests."""
    defaults = dict(
        scan=False,
        update_manifest=False,
        check_manifest=False,
        lines=None,
        since_last_run=False,
        mutate_all=False,
        max_workers=None,
        timeout_factor=10,
        min_timeout=1.0,
        pytest_args=None,
        test_contexts=None,
        cov_cmd=None,
        lcov=None,
        reuse_coverage=False,
        warning_threshold=50,
        manifest_file=False,
        verbose=False,
        exclude=None,
        prune_dirs=(),
        no_fork=False,
        build_test_contexts=None,
        files=[],
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


@pytest.mark.unit
def test_check_no_run_incompatibilities_test_contexts_raises():
    """--test-contexts paired with --scan (a no-run flag) must raise."""
    args = _make_args(scan=True, test_contexts=".coverage")
    with pytest.raises(ValidationError) as exc:
        _check_no_run_incompatibilities(args)
    assert exc.value.exit_code == 2
    assert "--test-contexts" in str(exc.value)


# ── Mutant-killing gap tests ──────────────────────────────────────────────────


@pytest.mark.unit
def test_check_coverage_flags_single_flag_allowed():
    # mutant_5: sum(cov_flags) > 1 — with only one flag, sum=1, must NOT raise
    args = argparse.Namespace(cov_cmd="echo hi", lcov=None, reuse_coverage=False)
    _check_coverage_flags(args)  # must not raise


@pytest.mark.unit
def test_check_coverage_flags_two_flags_raises():
    # mutant_2,3,6: sum > 1 → raise
    args = argparse.Namespace(cov_cmd="echo hi", lcov="/some/path", reuse_coverage=False)
    with pytest.raises(ValidationError) as exc:
        _check_coverage_flags(args)
    assert exc.value.exit_code == 2


@pytest.mark.unit
def test_check_coverage_flags_all_three_raises():
    args = argparse.Namespace(cov_cmd="echo", lcov="/f", reuse_coverage=True)
    with pytest.raises(ValidationError) as exc:
        _check_coverage_flags(args)
    assert exc.value.exit_code == 2


@pytest.mark.unit
def test_check_coverage_flags_error_text():
    args = argparse.Namespace(cov_cmd="echo", lcov="/f", reuse_coverage=False)
    with pytest.raises(ValidationError) as exc:
        _check_coverage_flags(args)
    assert "mutually exclusive" in str(exc.value)


@pytest.mark.unit
def test_max_workers_with_lines_parse_accepted():
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py", "--max-workers", "4", "--lines", "7"])
    # Should not raise
    _validate_mutual_exclusions(args)


@pytest.mark.unit
def test_max_workers_with_since_last_run_parse_accepted():
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py", "--max-workers", "4", "--since-last-run"])
    _validate_mutual_exclusions(args)


@pytest.mark.unit
def test_max_workers_with_mutate_all_parse_accepted():
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py", "--max-workers", "4", "--mutate-all"])
    _validate_mutual_exclusions(args)


# ── _validate_mutual_exclusions: direct unit coverage ─────────────────────────


@pytest.mark.unit
def test_validate_scan_and_update_manifest_raises():
    with pytest.raises(ValidationError) as exc:
        _validate_mutual_exclusions(_make_args(scan=True, update_manifest=True))
    assert exc.value.exit_code == 2
    assert "--scan" in str(exc.value)


@pytest.mark.unit
@pytest.mark.parametrize(
    "extra",
    [
        {"lines": "7"},
        {"since_last_run": True},
        {"mutate_all": True},
        {"max_workers": 4},
    ],
)
def test_validate_scan_with_run_only_flag_raises(extra):
    with pytest.raises(ValidationError) as exc:
        _validate_mutual_exclusions(_make_args(scan=True, **extra))
    assert exc.value.exit_code == 2
    assert "--scan" in str(exc.value)


@pytest.mark.unit
@pytest.mark.parametrize(
    "extra",
    [
        {"lines": "7"},
        {"since_last_run": True},
        {"mutate_all": True},
        {"max_workers": 4},
    ],
)
def test_validate_check_manifest_with_run_only_flag_raises(extra):
    with pytest.raises(ValidationError) as exc:
        _validate_mutual_exclusions(_make_args(check_manifest=True, **extra))
    assert exc.value.exit_code == 2
    assert "--check-manifest" in str(exc.value)


@pytest.mark.unit
def test_validate_update_manifest_with_lines_raises():
    with pytest.raises(ValidationError) as exc:
        _validate_mutual_exclusions(_make_args(update_manifest=True, lines="5"))
    assert exc.value.exit_code == 2
    assert "--update-manifest" in str(exc.value)


@pytest.mark.unit
@pytest.mark.parametrize(
    "extra",
    [
        {"since_last_run": True},
        {"mutate_all": True},
        {"max_workers": 4},
    ],
)
def test_validate_update_manifest_with_run_only_flag_raises(extra):
    with pytest.raises(ValidationError) as exc:
        _validate_mutual_exclusions(_make_args(update_manifest=True, **extra))
    assert exc.value.exit_code == 2
    assert "--update-manifest" in str(exc.value)


@pytest.mark.unit
def test_validate_scan_with_timeout_factor_raises():
    with pytest.raises(ValidationError) as exc:
        _validate_mutual_exclusions(_make_args(scan=True, timeout_factor=5))
    assert exc.value.exit_code == 2
    assert "--timeout-factor" in str(exc.value)


@pytest.mark.unit
def test_validate_scan_with_pytest_args_raises():
    with pytest.raises(ValidationError) as exc:
        _validate_mutual_exclusions(_make_args(scan=True, pytest_args="-k foo"))
    assert exc.value.exit_code == 2
    assert "--pytest-args" in str(exc.value)


@pytest.mark.unit
@pytest.mark.parametrize(
    "extra",
    [
        {"since_last_run": True, "mutate_all": True},
        {"since_last_run": True, "lines": "7"},
        {"mutate_all": True, "lines": "7"},
    ],
)
def test_validate_pairwise_selection_raises(extra):
    with pytest.raises(ValidationError) as exc:
        _validate_mutual_exclusions(_make_args(**extra))
    assert exc.value.exit_code == 2
    assert "pairwise exclusive" in str(exc.value)


@pytest.mark.unit
def test_validate_no_flags_passes():
    _validate_mutual_exclusions(_make_args())  # must not raise


@pytest.mark.unit
def test_validate_check_manifest_with_scan_raises():
    with pytest.raises(ValidationError) as exc:
        _validate_mutual_exclusions(_make_args(check_manifest=True, scan=True))
    assert exc.value.exit_code == 2
    assert "--check-manifest" in str(exc.value)


@pytest.mark.unit
def test_validate_check_manifest_with_update_manifest_raises():
    with pytest.raises(ValidationError) as exc:
        _validate_mutual_exclusions(_make_args(check_manifest=True, update_manifest=True))
    assert exc.value.exit_code == 2
    assert "--check-manifest" in str(exc.value)


# ── --build-test-contexts ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_validate_build_test_contexts_alone_passes():
    _validate_mutual_exclusions(_make_args(build_test_contexts="out.db"))  # must not raise


@pytest.mark.unit
@pytest.mark.parametrize("other", ["scan", "update_manifest", "check_manifest"])
def test_validate_build_test_contexts_with_another_no_run_mode_raises(other):
    with pytest.raises(ValidationError) as exc:
        _validate_mutual_exclusions(_make_args(build_test_contexts="out.db", **{other: True}))
    assert exc.value.exit_code == 2
    assert "--build-test-contexts" in str(exc.value)


@pytest.mark.unit
@pytest.mark.parametrize(
    "extra",
    [
        {"lines": "7"},
        {"since_last_run": True},
        {"mutate_all": True},
        {"max_workers": 4},
        {"test_contexts": ".coverage"},
    ],
)
def test_validate_build_test_contexts_with_run_only_flag_raises(extra):
    with pytest.raises(ValidationError) as exc:
        _validate_mutual_exclusions(_make_args(build_test_contexts="out.db", **extra))
    assert exc.value.exit_code == 2
    assert "--build-test-contexts" in str(exc.value)


@pytest.mark.unit
def test_validate_build_test_contexts_with_positional_files_raises():
    with pytest.raises(ValidationError) as exc:
        _validate_mutual_exclusions(_make_args(build_test_contexts="out.db", files=["f.py"]))
    assert exc.value.exit_code == 2
    assert "--build-test-contexts" in str(exc.value)
