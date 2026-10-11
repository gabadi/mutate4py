"""Unit tests for mutate4py._cli_validation (issue #38 gate 12).

Assert on raised errors, not process exit and captured stderr — this module
never calls sys.exit or print (that's the CLI adapter's job; see
tests/test_main.py for adapter-level coverage of exit codes and stderr
text, via subprocess CLI invocations and in-process main()/argv tests).
"""

import argparse
import os
import sys

import pytest

from mutate4py import _cli_validation
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
        allow_survivors=False,
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


# ── check_project_env (foreign-interpreter guard) ───────────────────────────


def _make_project(root, *, venv: bool) -> str:
    """Create a project root with pyproject.toml and, optionally, a .venv
    python. Return the absolute venv path (whether or not it exists)."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    venv_dir = root / ".venv"
    if venv:
        (venv_dir / "bin").mkdir(parents=True)
        (venv_dir / "bin" / "python").write_text("")
    return os.path.abspath(venv_dir)


def _mismatch_message(running: str, env: str) -> str:
    return (
        f"mutate4py is running under {running}, not the project environment {env}. "
        "From the project root, run `uv run --with mutate4py mutate4py <same arguments>`, "
        f"or `{env}/bin/python -m mutate4py <same arguments>` if mutate4py is installed there, "
        "so tests use the project's own dependencies."
    )


@pytest.mark.unit
def test_check_project_env_mismatch_raises_exit_2_with_exact_message(tmp_path):
    root = tmp_path / "proj"
    env = _make_project(root, venv=True)
    target = str(root / "src" / "demo" / "__init__.py")
    with pytest.raises(ValidationError) as exc:
        _cli_validation.check_project_env([target], cwd=str(tmp_path), running_prefix="/opt/other")
    assert exc.value.exit_code == 2
    assert str(exc.value) == _mismatch_message("/opt/other", env)


@pytest.mark.unit
def test_check_project_env_matching_prefix_passes(tmp_path):
    root = tmp_path / "proj"
    env = _make_project(root, venv=True)
    target = str(root / "src" / "demo" / "__init__.py")
    _cli_validation.check_project_env([target], cwd=str(tmp_path), running_prefix=env)


@pytest.mark.unit
def test_check_project_env_symlinked_venv_passes_when_prefix_is_the_real_venv(tmp_path):
    """A `.venv` symlink points at the real venv the running interpreter
    reports as its prefix: same environment, so nothing is rejected."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    real_venv = tmp_path / "shared-venv"
    (real_venv / "bin").mkdir(parents=True)
    (real_venv / "bin" / "python").write_text("")
    os.symlink(real_venv, root / ".venv")
    target = str(root / "src" / "demo" / "__init__.py")
    _cli_validation.check_project_env([target], cwd=str(tmp_path), running_prefix=str(real_venv))
    with pytest.raises(ValidationError):
        _cli_validation.check_project_env([target], cwd=str(tmp_path), running_prefix="/opt/other")


@pytest.mark.unit
def test_check_project_env_symlinked_project_root_passes_when_prefix_is_the_real_venv(tmp_path):
    """The target is reached through a symlinked project directory; the real
    venv is the one the running interpreter reports, so nothing is rejected."""
    real_root = tmp_path / "real-proj"
    real_env = _make_project(real_root, venv=True)
    linked_root = tmp_path / "linked-proj"
    os.symlink(real_root, linked_root)
    target = str(linked_root / "src" / "demo" / "__init__.py")
    _cli_validation.check_project_env([target], cwd=str(tmp_path), running_prefix=real_env)
    with pytest.raises(ValidationError):
        _cli_validation.check_project_env([target], cwd=str(tmp_path), running_prefix="/opt/other")


@pytest.mark.unit
def test_check_project_env_without_venv_passes(tmp_path):
    root = tmp_path / "proj"
    _make_project(root, venv=False)
    target = str(root / "src" / "demo" / "__init__.py")
    _cli_validation.check_project_env([target], cwd=str(tmp_path), running_prefix="/opt/other")


@pytest.mark.unit
def test_check_project_env_nested_target_uses_nearest_pyproject_root(tmp_path):
    """The outer project's venv would mismatch, but the nearest root is the
    inner project, whose venv matches: nothing must be raised."""
    outer = tmp_path / "outer"
    _make_project(outer, venv=True)
    inner = outer / "packages" / "inner"
    inner_env = _make_project(inner, venv=True)
    target = str(inner / "src" / "demo" / "mod.py")
    _cli_validation.check_project_env([target], cwd=str(tmp_path), running_prefix=inner_env)


@pytest.mark.unit
def test_check_project_env_nested_target_names_the_nearest_root_env(tmp_path):
    outer = tmp_path / "outer"
    _make_project(outer, venv=True)
    inner = outer / "packages" / "inner"
    inner_env = _make_project(inner, venv=True)
    target = str(inner / "src" / "demo" / "mod.py")
    with pytest.raises(ValidationError) as exc:
        _cli_validation.check_project_env([target], cwd=str(tmp_path), running_prefix="/opt/other")
    assert _mismatch_message("/opt/other", inner_env) == str(exc.value)


@pytest.mark.unit
def test_check_project_env_relative_target_resolves_against_cwd(tmp_path):
    root = tmp_path / "proj"
    env = _make_project(root, venv=True)
    with pytest.raises(ValidationError) as exc:
        _cli_validation.check_project_env(["src/demo/__init__.py"], cwd=str(root), running_prefix="/opt/other")
    assert env in str(exc.value)


@pytest.mark.unit
def test_check_project_env_without_paths_checks_cwd(tmp_path):
    root = tmp_path / "proj"
    env = _make_project(root, venv=True)
    with pytest.raises(ValidationError) as exc:
        _cli_validation.check_project_env([], cwd=str(root), running_prefix="/opt/other")
    assert env in str(exc.value)


@pytest.mark.unit
def test_check_project_env_checks_cwd_even_when_targets_are_given(tmp_path):
    """Workspace autodiscovery resolves to the cwd's `.venv` even when a member
    target is named, so a member without its own `.venv` must not hide it."""
    workspace = tmp_path / "ws"
    env = _make_project(workspace, venv=True)
    member = workspace / "packages" / "member"
    _make_project(member, venv=False)
    target = str(member / "src" / "demo" / "__init__.py")
    with pytest.raises(ValidationError) as exc:
        _cli_validation.check_project_env([target], cwd=str(workspace), running_prefix="/opt/other")
    assert env in str(exc.value)


@pytest.mark.unit
@pytest.mark.parametrize("no_run_flag", ["scan", "update_manifest", "check_manifest"])
def test_check_run_env_skips_no_run_modes(tmp_path, no_run_flag):
    root = tmp_path / "proj"
    _make_project(root, venv=True)
    args = _make_args(**{no_run_flag: True})
    _cli_validation.check_run_env(args, [], cwd=str(root), running_prefix="/opt/other")


@pytest.mark.unit
def test_check_run_env_checks_run_modes(tmp_path):
    root = tmp_path / "proj"
    env = _make_project(root, venv=True)
    with pytest.raises(ValidationError) as exc:
        _cli_validation.check_run_env(_make_args(), [], cwd=str(root), running_prefix="/opt/other")
    assert env in str(exc.value)


def _make_site_packages(env: str) -> str:
    """Create the project venv's site-packages dir, as a real venv has one."""
    site = os.path.join(env, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages")
    os.makedirs(site)
    return site


@pytest.mark.unit
def test_check_project_env_uv_run_overlay_passes_when_project_site_packages_on_sys_path(tmp_path):
    """`uv run --with <path>` runs under a temporary overlay prefix, but it puts
    the project's site-packages on sys.path: that overlay is the project
    environment (ADR 0025)."""
    root = tmp_path / "proj"
    env = _make_project(root, venv=True)
    site = _make_site_packages(env)
    target = str(root / "src" / "demo" / "__init__.py")
    _cli_validation.check_project_env(
        [target],
        cwd=str(tmp_path),
        running_prefix="/overlay/prefix",
        sys_path=["/overlay/prefix/lib/python3.13/site-packages", site],
    )


@pytest.mark.unit
def test_check_project_env_foreign_env_without_project_site_packages_still_exits_2(tmp_path):
    root = tmp_path / "proj"
    env = _make_project(root, venv=True)
    _make_site_packages(env)
    target = str(root / "src" / "demo" / "__init__.py")
    with pytest.raises(ValidationError) as exc:
        _cli_validation.check_project_env(
            [target],
            cwd=str(tmp_path),
            running_prefix="/opt/other",
            sys_path=["/opt/other/lib/python3.13/site-packages"],
        )
    assert exc.value.exit_code == 2
    assert str(exc.value) == _mismatch_message("/opt/other", env)


@pytest.mark.unit
def test_check_project_env_pythonpath_site_packages_still_exits_2(tmp_path, monkeypatch):
    """PYTHONPATH is not site processing: a project site-packages named only
    there does not make a foreign interpreter the project's environment."""
    root = tmp_path / "proj"
    env = _make_project(root, venv=True)
    site = _make_site_packages(env)
    monkeypatch.setenv("PYTHONPATH", site)
    monkeypatch.setattr(sys, "path", [site, *sys.path])
    target = str(root / "src" / "demo" / "__init__.py")
    with pytest.raises(ValidationError) as exc:
        _cli_validation.check_project_env([target], cwd=str(tmp_path), running_prefix="/opt/other")
    assert exc.value.exit_code == 2


@pytest.mark.unit
def test_check_project_env_other_minor_version_site_packages_still_exits_2(tmp_path):
    """A venv's site-packages for another Python minor version is not the running
    interpreter's environment, even when it is on sys.path."""
    root = tmp_path / "proj"
    env = _make_project(root, venv=True)
    other = os.path.join(env, "lib", "python9.9", "site-packages")
    os.makedirs(other)
    target = str(root / "src" / "demo" / "__init__.py")
    with pytest.raises(ValidationError) as exc:
        _cli_validation.check_project_env(
            [target],
            cwd=str(tmp_path),
            running_prefix="/opt/other",
            sys_path=[other],
        )
    assert exc.value.exit_code == 2
