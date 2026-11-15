"""Unit tests for mutate4py CLI entry point (__main__): flag parsing, validation,
and --help/--check-manifest/--manifest-file behavior. Split from test_main.py
(issue #71 migration pushed it over the module size guard's 1000-line cap)."""

import os
import subprocess
import sys

import pytest


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _help_text(monkeypatch, capsys) -> str:
    """Print `mutate4py --help` in-process and return it. argparse exits 0 after printing the help."""
    from mutate4py.__main__ import main

    monkeypatch.setattr(sys, "argv", ["mutate4py", "--help"])
    with pytest.raises(SystemExit) as exit_info:
        main()
    assert exit_info.value.code == 0
    return capsys.readouterr().out


# ── _build_parser: dest and flag-name mutants ─────────────────────────────────


@pytest.mark.unit
def test_build_parser_lcov_dest_is_lcov():
    # mutant_8: dest=None → --lcov value stored as None key (unreachable as args.lcov)
    # mutant_11: dest omitted → argparse derives "lcov" from "--lcov" (equivalent)
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["somefile.py", "--lcov", "/path/to/cov.info"])
    assert args.lcov == "/path/to/cov.info"


@pytest.mark.unit
def test_build_parser_defaults_no_flags():
    # mutant_12: default=None omitted; mutmut_18: --mutate-all default is False
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["somefile.py"])
    assert args.lcov is None
    assert args.mutate_all is False


@pytest.mark.unit
def test_build_parser_mutate_all_flag_is_parsed_for_refusal():
    # The removed flag stays parseable (hidden, spec #115) so _check_removed_flags can refuse it.
    # mutant_18: "--mutate-all" → "--MUTATE-ALL" (different flag name)
    # Correct: --mutate-all must be parseable and set mutate_all=True
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["somefile.py", "--mutate-all"])
    assert args.mutate_all is True


@pytest.mark.unit
def test_build_parser_mutation_warning_sets_its_value_and_defaults_to_50():
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    assert parser.parse_args(["somefile.py", "--mutation-warning", "25"]).warning_threshold == 25
    assert parser.parse_args(["somefile.py"]).warning_threshold == 50


@pytest.mark.unit
def test_build_parser_timeout_flags_default_to_factor_10_and_a_5_second_floor():
    # The Mutant timeout is max(--min-timeout, factor x budget) + overhead; these are its two inputs.
    from mutate4py.__main__ import _build_parser

    args = _build_parser().parse_args(["somefile.py"])
    assert args.timeout_factor == 10
    assert args.min_timeout == 5.0


@pytest.mark.unit
def test_build_parser_timeout_flags_set_their_values():
    from mutate4py.__main__ import _build_parser

    args = _build_parser().parse_args(["somefile.py", "--timeout-factor", "3", "--min-timeout", "0.25"])
    assert args.timeout_factor == 3
    assert args.min_timeout == 0.25


# ── F5: --max-workers flag ────────────────────────────────────────────────────


@pytest.mark.unit
def test_build_parser_max_workers_sets_value():
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py", "--max-workers", "4"])
    assert args.max_workers == 4


@pytest.mark.unit
def test_build_parser_flag_defaults():
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py"])
    assert args.max_workers is None
    assert args.verbose is False


@pytest.mark.unit
def test_build_parser_manifest_file_dest_is_manifest_file():
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py", "--manifest-file"])
    assert args.manifest_file is True


@pytest.mark.unit
def test_build_parser_pytest_args_defaults_none():
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py"])
    assert args.pytest_args is None


@pytest.mark.unit
def test_build_parser_pytest_args_sets_raw_string():
    """--pytest-args is stored raw here; _dispatch tokenizes it (see test_dispatch.py)."""
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py", "--pytest-args", "-x -k foo"])
    assert args.pytest_args == "-x -k foo"


@pytest.mark.unit
def test_build_parser_rejects_test_command():
    """--test-command no longer exists; passing it is a usage error."""
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["f.py", "--test-command", "pytest"])
    assert exc.value.code == 2


@pytest.mark.unit
def test_build_parser_no_fork_defaults_false():
    """The forking executor fast path is on by default: --no-fork absent -> False."""
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py"])
    assert args.no_fork is False


@pytest.mark.unit
def test_build_parser_no_fork_flag_sets_true():
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py", "--no-fork"])
    assert args.no_fork is True


@pytest.mark.unit
def test_build_parser_manifest_file_defaults_to_false():
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py"])
    assert args.manifest_file is False


# ── F5: --mutation-warning default is 50 ─────────────────────────────────────


@pytest.mark.unit
def test_mutation_warning_default_is_50():
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py"])
    assert args.warning_threshold == 50


# ── F5: mutual exclusion — --scan / --update-manifest ────────────────────────
#
# Coverage for these flag-exclusivity combinations lives with the in-process
# `_validate_mutual_exclusions` unit tests in tests/test_cli_validation.py:
# they exercise pure argparse-namespace validation logic with no
# filesystem/process dependency, so a subprocess round-trip adds cost
# without adding coverage.


# ── F5: --help ────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_help_lists_manifest_file(monkeypatch, capsys):
    assert "--manifest-file" in _help_text(monkeypatch, capsys)


@pytest.mark.unit
def test_help_lists_exclude(monkeypatch, capsys):
    assert "--exclude" in _help_text(monkeypatch, capsys)


@pytest.mark.unit
def test_build_parser_declares_the_file_scratch_field():
    """args.file is a declared field of the parser's Namespace, not an
    attribute _dispatch injects unannounced (issue #22 review)."""
    from mutate4py.__main__ import _build_parser

    args = _build_parser().parse_args(["a.py"])
    assert args.files == ["a.py"]
    assert args.file is None


# ── F5: unknown flag / missing file ──────────────────────────────────────────


@pytest.mark.system
def test_no_positional_file_is_usage_error():
    result = subprocess.run(
        [sys.executable, "-m", "mutate4py"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": os.path.join(REPO_ROOT, "src")},
    )
    assert result.returncode != 0


# ── F5: --verbose flag ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_verbose_flag_parses():
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["f.py", "--verbose"])
    assert args.verbose is True


# ── _positive_int: error branches ────────────────────────────────────────────


@pytest.mark.unit
def test_positive_int_non_integer_raises():
    import argparse
    from mutate4py.__main__ import _positive_int

    try:
        _positive_int("abc")
        assert False, "expected ArgumentTypeError"
    except argparse.ArgumentTypeError as exc:
        assert "not a valid integer" in str(exc)


@pytest.mark.unit
def test_positive_int_zero_raises():
    import argparse
    from mutate4py.__main__ import _positive_int

    try:
        _positive_int("0")
        assert False, "expected ArgumentTypeError"
    except argparse.ArgumentTypeError as exc:
        assert "positive integer" in str(exc)


@pytest.mark.unit
def test_positive_int_negative_raises():
    import argparse
    from mutate4py.__main__ import _positive_int

    try:
        _positive_int("-5")
        assert False, "expected ArgumentTypeError"
    except argparse.ArgumentTypeError as exc:
        assert "positive integer" in str(exc)


# ── --check-manifest: single file ────────────────────────────────────────────


def _run_cli_path(path: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "mutate4py", path] + list(args),
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": os.path.join(REPO_ROOT, "src")},
        timeout=30,
    )


@pytest.mark.system
def test_check_manifest_missing_exits_1(tmp_path):
    p = tmp_path / "mod.py"
    p.write_text("def f(a, b):\n    return a > b\n")
    result = _run_cli_path(str(p), "--check-manifest")
    assert result.returncode == 1
    assert "Manifest missing:" in result.stdout


@pytest.mark.system
def test_check_manifest_current_exits_0(tmp_path):
    p = tmp_path / "mod.py"
    p.write_text("def f(a, b):\n    return a > b\n")
    setup = _run_cli_path(str(p), "--update-manifest")
    assert setup.returncode == 0
    result = _run_cli_path(str(p), "--check-manifest")
    assert result.returncode == 0
    assert "Manifest current:" in result.stdout


@pytest.mark.unit
def test_check_manifest_in_help(monkeypatch, capsys):
    assert "--check-manifest" in _help_text(monkeypatch, capsys)


# ── --manifest-file: single file end-to-end ────────────────────────────────────


@pytest.mark.system
def test_manifest_file_update_writes_sidecar_and_footer_free_source(tmp_path):
    import json

    p = tmp_path / "mod.py"
    p.write_text("def f(a, b):\n    return a > b\n")
    sidecar = tmp_path / "mod.py.manifest.json"

    result = _run_cli_path(str(p), "--update-manifest", "--manifest-file")

    assert result.returncode == 0
    assert "Updated manifest:" in result.stdout
    assert sidecar.is_file()
    sidecar_data = json.loads(sidecar.read_text())
    assert sidecar_data["functions"][0]["id"] == "func/f"
    assert "mutate4py-manifest-begin" not in p.read_text()


@pytest.mark.system
def test_manifest_file_check_reads_sidecar(tmp_path):
    p = tmp_path / "mod.py"
    p.write_text("def f(a, b):\n    return a > b\n")
    _run_cli_path(str(p), "--update-manifest", "--manifest-file")

    result = _run_cli_path(str(p), "--check-manifest", "--manifest-file")

    assert result.returncode == 0
    assert "Manifest current:" in result.stdout


@pytest.mark.system
def test_manifest_file_check_missing_sidecar_reports_missing(tmp_path):
    p = tmp_path / "mod.py"
    p.write_text("def f(a, b):\n    return a > b\n")

    result = _run_cli_path(str(p), "--check-manifest", "--manifest-file")

    assert result.returncode == 1
    assert "Manifest missing:" in result.stdout


@pytest.mark.unit
def test_check_manifest_help_states_what_it_checks_and_what_it_does_not():
    from mutate4py.__main__ import _build_parser

    help_text = " ".join(_build_parser().format_help().split())

    assert "checks hashes, recorded Survivors and equivalent markers, not tests digests" in help_text
