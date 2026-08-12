"""Unit tests for acceptance/steps/cli_surface_helpers.py."""

import pytest

from acceptance.steps.cli_surface_helpers import (
    accepted_flags_args,
    assert_accepted,
    assert_dispatched_to,
    assert_no_analysis,
    assert_nonzero_exit,
    assert_only_reported,
    assert_option_accepted,
    assert_usage_error,
    assert_usage_lists_max_workers,
    assert_usage_printed,
    assert_worker_count,
    assert_zero_exit,
    default_source,
    described_args,
    exclude_run_args,
    lcov_content,
    reported_manifest_files,
    require_result,
    single_flag_args,
    split_flags,
    two_flag_args,
)


# ── split_flags ───────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_split_flags_simple():
    assert split_flags("--scan") == ["--scan"]


@pytest.mark.unit
def test_split_flags_with_value():
    assert split_flags("--max-workers 4") == ["--max-workers", "4"]


@pytest.mark.unit
def test_split_flags_quoted_value():
    assert split_flags('--pytest-args "-x -k foo"') == ["--pytest-args", "-x -k foo"]


# ── default_source / lcov_content ─────────────────────────────────────────────


@pytest.mark.unit
def test_default_source_is_nonempty():
    src = default_source()
    assert "def calc" in src


@pytest.mark.unit
def test_lcov_content_includes_sf():
    content = lcov_content("/tmp/foo.py")
    assert "SF:/tmp/foo.py" in content
    assert "DA:2,1" in content
    assert "end_of_record" in content


# ── single_flag_args ──────────────────────────────────────────────────────────


@pytest.mark.unit
def test_single_flag_none_gives_scan():
    args = single_flag_args("(none)", "s.py", "cov.lcov")
    assert args == ["s.py", "--scan"]


@pytest.mark.unit
def test_single_flag_scan_incompatible_gives_lcov_run():
    args = single_flag_args("--max-workers 4", "s.py", "cov.lcov")
    assert "--lcov" in args
    assert "--max-workers" in args


@pytest.mark.unit
def test_single_flag_pytest_args_gives_lcov_run():
    args = single_flag_args("--pytest-args -x", "s.py", "cov.lcov")
    assert "--lcov" in args
    assert "--pytest-args" in args


@pytest.mark.unit
def test_single_flag_regular_adds_scan():
    args = single_flag_args("--mutation-warning 10", "s.py", "cov.lcov")
    assert "--scan" in args
    assert "--mutation-warning" in args


# ── two_flag_args ─────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_two_flag_args_nothing_and_flag():
    args = two_flag_args("(nothing)", "--scan", "s.py", "cov.lcov")
    assert "--scan" in args


@pytest.mark.unit
def test_two_flag_args_max_workers_without_scan_gives_lcov_run():
    args = two_flag_args("--max-workers 4", "--since-last-run", "s.py", "cov.lcov")
    assert "--lcov" in args
    assert "--max-workers" in args


@pytest.mark.unit
def test_two_flag_args_max_workers_with_scan_gives_plain_run():
    args = two_flag_args("--scan", "--max-workers 4", "s.py", "cov.lcov")
    assert "--lcov" not in args
    assert "--scan" in args


# ── described_args ────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_described_args_bogus_flag():
    args = described_args("a valid file with --bogus-flag", "s.py")
    assert "--bogus-flag" in args


@pytest.mark.unit
def test_described_args_no_positional():
    args = described_args("no positional source file", "s.py")
    assert "--scan" in args
    assert "s.py" not in args


@pytest.mark.unit
def test_described_args_nonexistent_path():
    args = described_args("a source path that does not exist", "s.py")
    assert "/nonexistent" in args[0]


@pytest.mark.unit
def test_described_args_unknown_raises():
    with pytest.raises(NotImplementedError):
        described_args("unknown description", "s.py")


# ── accepted_flags_args ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_accepted_flags_scan():
    args, target, workers = accepted_flags_args("--scan", "s.py", "cov.lcov")
    assert "--scan" in args
    assert target == "scan surface"
    assert workers is None


@pytest.mark.unit
def test_accepted_flags_update_manifest():
    args, target, workers = accepted_flags_args("--update-manifest", "s.py", "cov.lcov")
    assert "--update-manifest" in args
    assert target == "manifest write"
    assert workers is None


@pytest.mark.unit
def test_accepted_flags_coverage():
    args, target, workers = accepted_flags_args("(a coverage flag)", "s.py", "cov.lcov")
    assert "--lcov" in args
    assert target == "run loop"
    assert workers is None


@pytest.mark.unit
def test_accepted_flags_max_workers():
    args, target, workers = accepted_flags_args("--max-workers 4 (a coverage flag)", "s.py", "cov.lcov")
    assert "--max-workers" in args
    assert target == "run loop"
    assert workers == 4


@pytest.mark.unit
def test_accepted_flags_unknown_raises():
    with pytest.raises(NotImplementedError):
        accepted_flags_args("--unknown-combo", "s.py", "cov.lcov")


# ── require_result ────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_require_result_none_raises():
    with pytest.raises(AssertionError):
        require_result(None)


@pytest.mark.unit
def test_require_result_returns_value():
    obj = object()
    assert require_result(obj) is obj


# ── assert_accepted ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_assert_accepted_passes_on_zero():
    assert_accepted(0, "", "")


@pytest.mark.unit
def test_assert_accepted_fails_on_nonzero():
    with pytest.raises(AssertionError):
        assert_accepted(1, "out", "err")


# ── assert_usage_error ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_assert_usage_error_passes_on_nonzero():
    assert_usage_error(2, "", "")


@pytest.mark.unit
def test_assert_usage_error_fails_on_zero():
    with pytest.raises(AssertionError):
        assert_usage_error(0, "out", "err")


# ── assert_nonzero_exit ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_assert_nonzero_exit_passes():
    assert_nonzero_exit(1)


@pytest.mark.unit
def test_assert_nonzero_exit_fails_on_zero():
    with pytest.raises(AssertionError):
        assert_nonzero_exit(0)


# ── assert_zero_exit ──────────────────────────────────────────────────────────


@pytest.mark.unit
def test_assert_zero_exit_passes():
    assert_zero_exit(0, "")


@pytest.mark.unit
def test_assert_zero_exit_fails_on_nonzero():
    with pytest.raises(AssertionError):
        assert_zero_exit(1, "err")


# ── assert_no_analysis ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_assert_no_analysis_passes_on_clean():
    assert_no_analysis("")


@pytest.mark.unit
def test_assert_no_analysis_fails_on_scan():
    with pytest.raises(AssertionError):
        assert_no_analysis("Mutation scan: foo.py")


@pytest.mark.unit
def test_assert_no_analysis_fails_on_run():
    with pytest.raises(AssertionError):
        assert_no_analysis("Mutation run:")


# ── assert_usage_printed ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_assert_usage_printed_with_usage():
    assert_usage_printed("usage: mutate4py ...")


@pytest.mark.unit
def test_assert_usage_printed_with_mutate4py():
    assert_usage_printed("mutate4py [options]")


@pytest.mark.unit
def test_assert_usage_printed_fails_on_empty():
    with pytest.raises(AssertionError):
        assert_usage_printed("")


# ── assert_usage_lists_max_workers ────────────────────────────────────────────


@pytest.mark.unit
def test_assert_usage_lists_max_workers_passes():
    assert_usage_lists_max_workers("  --max-workers N  number of workers")


@pytest.mark.unit
def test_assert_usage_lists_max_workers_fails():
    with pytest.raises(AssertionError):
        assert_usage_lists_max_workers("usage: mutate4py [options]")


# ── assert_worker_count ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_assert_worker_count_passes():
    assert_worker_count(4, "4", 0, "")


@pytest.mark.unit
def test_assert_worker_count_fails_on_nonzero():
    with pytest.raises(AssertionError):
        assert_worker_count(4, "4", 1, "some error")


@pytest.mark.unit
def test_assert_worker_count_fails_on_mismatch():
    with pytest.raises(AssertionError):
        assert_worker_count(2, "4", 0, "")


# ── assert_dispatched_to ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_assert_dispatched_scan_passes():
    assert_dispatched_to("scan surface", 0, "Mutation scan: foo.py", "")


@pytest.mark.unit
def test_assert_dispatched_scan_fails():
    with pytest.raises(AssertionError):
        assert_dispatched_to("scan surface", 0, "nothing here", "")


@pytest.mark.unit
def test_assert_dispatched_manifest_passes():
    assert_dispatched_to("manifest write", 0, "Updated manifest: foo.py", "")


@pytest.mark.unit
def test_assert_dispatched_run_loop_passes_on_zero():
    assert_dispatched_to("run loop", 0, "no output", "")


@pytest.mark.unit
def test_assert_dispatched_run_loop_passes_on_output():
    assert_dispatched_to("run loop", 1, "Mutation run: foo.py", "")


@pytest.mark.unit
def test_assert_dispatched_unknown_raises():
    with pytest.raises(NotImplementedError):
        assert_dispatched_to("unknown target", 0, "", "")


# ── assert_option_accepted ────────────────────────────────────────────────────


@pytest.mark.unit
def test_assert_option_mutation_warning_default():
    assert_option_accepted("mutation-warning", "50", 0, "")


@pytest.mark.unit
def test_assert_option_mutation_warning_custom():
    assert_option_accepted("mutation-warning", "25", 0, "")


@pytest.mark.unit
def test_assert_option_mutation_warning_custom_fails_on_nonzero():
    with pytest.raises(AssertionError):
        assert_option_accepted("mutation-warning", "25", 1, "error")


@pytest.mark.unit
def test_assert_option_timeout_factor_default():
    assert_option_accepted("timeout-factor", "10", 0, "")


@pytest.mark.unit
def test_assert_option_pytest_args_default():
    assert_option_accepted("pytest-args", "", 0, "")


@pytest.mark.unit
def test_assert_option_max_workers_serial():
    assert_option_accepted("max-workers", "serial", 0, "")


@pytest.mark.unit
def test_assert_option_max_workers_value():
    assert_option_accepted("max-workers", "4", 0, "")


@pytest.mark.unit
def test_assert_option_max_workers_value_fails():
    with pytest.raises(AssertionError):
        assert_option_accepted("max-workers", "4", 1, "err")


# ── --exclude helpers ─────────────────────────────────────────────────────────


@pytest.mark.unit
def test_exclude_run_args_appends_pattern_after_mode_flag():
    assert exclude_run_args("--check-manifest", "*/skip.py", "/tmp/pkg") == [
        "/tmp/pkg",
        "--check-manifest",
        "--exclude",
        "*/skip.py",
    ]


@pytest.mark.unit
def test_reported_manifest_files_collects_basenames_in_order():
    stdout = (
        "Manifest missing: /tmp/pkg/keep.py\nManifest current: /tmp/pkg/other.py\nManifest stale: /tmp/pkg/third.py\n"
    )
    assert reported_manifest_files(stdout) == ["keep.py", "other.py", "third.py"]


@pytest.mark.unit
def test_reported_manifest_files_ignores_unrelated_lines():
    assert reported_manifest_files("Mutation scan: /tmp/pkg/keep.py\nManifest exists: false\n") == []


@pytest.mark.unit
def test_assert_only_reported_passes_for_a_single_match():
    assert_only_reported("Manifest missing: /tmp/pkg/keep.py\n", "keep.py")


@pytest.mark.unit
def test_assert_only_reported_fails_when_another_file_appears():
    stdout = "Manifest missing: /tmp/pkg/keep.py\nManifest missing: /tmp/pkg/skip.py\n"
    with pytest.raises(AssertionError):
        assert_only_reported(stdout, "keep.py")


@pytest.mark.unit
def test_assert_only_reported_fails_when_nothing_is_reported():
    with pytest.raises(AssertionError):
        assert_only_reported("", "keep.py")
