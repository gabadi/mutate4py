"""Survivor gate (#76): a scored run with an unaccepted survivor exits 3.

Component tests drive run_mutations in-process with real pytest subprocesses.
Unit tests cover the --allow-survivors flag, its rejection in no-run modes,
and its wiring from the CLI namespace into the run request.
"""

import io
import os
from contextlib import redirect_stdout

import pytest

from ._pytest_project_helpers import (
    write_always_passing_pytest_project,
    write_content_check_pytest_project,
    write_sleep_if_mutated_pytest_project,
)
from mutate4py._discovery import discover_sites
from mutate4py._runner import RunMutationsRequest, check_manifest, run_mutations, update_manifest

_SRC = "def f(a, b):\n    return a > b\n"
_TWO_FUNCTIONS = "def f(a, b):\n    return a > b\n\n\ndef g(a, b):\n    return a > b\n"


def _write_source_and_lcov(tmp_path, source=_SRC):
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(source)
    sites = discover_sites(source)
    lcov_path = str(tmp_path / "cov.lcov")
    da_lines = "\n".join(f"DA:{s.line},1" for s in sites)
    with open(lcov_path, "w") as f:
        f.write(f"SF:{src_path}\n{da_lines}\nend_of_record\n")
    return src_path, lcov_path, sites


def _request(tmp_path, src_path, lcov_path, pytest_args, **extra):
    return RunMutationsRequest(
        path=src_path,
        source=extra.pop("source", _SRC),
        cov_cmd=None,
        lcov_path=lcov_path,
        reuse_coverage=False,
        pytest_args=pytest_args,
        timeout_factor=extra.pop("timeout_factor", 10),
        min_timeout=extra.pop("min_timeout", 1.0),
        lines_filter=None,
        since_last_run=False,
        mutate_all=extra.pop("mutate_all", False),
        warning_threshold=1000,
        cwd=str(tmp_path),
        **extra,
    )


def _run(tmp_path, src_path, lcov_path, pytest_args, **extra):
    request = _request(tmp_path, src_path, lcov_path, pytest_args, **extra)
    with redirect_stdout(io.StringIO()):
        return run_mutations(request)


@pytest.mark.component
def test_run_mutations_returns_3_when_a_mutant_survives(tmp_path):
    src_path, lcov_path, _ = _write_source_and_lcov(tmp_path)
    pytest_args = write_always_passing_pytest_project(str(tmp_path))

    assert _run(tmp_path, src_path, lcov_path, pytest_args) == 3


@pytest.mark.component
def test_run_mutations_returns_0_when_survivors_allowed(tmp_path):
    src_path, lcov_path, _ = _write_source_and_lcov(tmp_path)
    pytest_args = write_always_passing_pytest_project(str(tmp_path))

    assert _run(tmp_path, src_path, lcov_path, pytest_args, allow_survivors=True) == 0


@pytest.mark.component
def test_run_mutations_timeout_is_not_a_survivor(tmp_path):
    # A mutant that exceeds the timeout is Killed, so the run exits 0.
    # A fast pass would be a survivor and exit 3, so 0 proves the timeout path.
    src_path, lcov_path, sites = _write_source_and_lcov(tmp_path)
    pytest_args = write_sleep_if_mutated_pytest_project(str(tmp_path), src_path, sites[0].mutant_text, 5)

    assert _run(tmp_path, src_path, lcov_path, pytest_args, timeout_factor=1, min_timeout=0.1) == 0


@pytest.mark.component
def test_run_mutations_exits_0_when_every_survivor_is_accepted(tmp_path):
    # The marker accepts the survivor, so the run does not exit 3 and the reason is recorded.
    marked = "def f(a, b):\n    return a > b  # mutate4py: equivalent same for all inputs\n"
    src_path, lcov_path, _ = _write_source_and_lcov(tmp_path, marked)
    pytest_args = write_always_passing_pytest_project(str(tmp_path))

    assert _run(tmp_path, src_path, lcov_path, pytest_args, source=marked, manifest_file=True) == 0

    fn = _recorded_function(src_path)
    assert fn["survivors"] == []
    assert fn["accepted"][0]["reason"] == "same for all inputs"


@pytest.mark.component
def test_empty_marker_reason_returns_2_before_baseline(tmp_path):
    # An empty reason is a usage error, raised before any .bak is written or the source is touched.
    bare = "def f(a, b):\n    return a > b  # mutate4py: equivalent\n"
    src_path, lcov_path, _ = _write_source_and_lcov(tmp_path, bare)
    pytest_args = write_always_passing_pytest_project(str(tmp_path))
    request = _request(tmp_path, src_path, lcov_path, pytest_args, source=bare)

    out = io.StringIO()
    with redirect_stdout(out):
        code = run_mutations(request)

    assert code == 2
    assert not os.path.exists(src_path + ".bak")
    with open(src_path) as f:
        assert f.read() == bare
    assert "Mutation Report" not in out.getvalue()


@pytest.mark.unit
def test_allow_survivors_defaults_false_and_parses():
    from mutate4py.__main__ import _build_parser

    parser = _build_parser()

    assert parser.parse_args(["calc.py"]).allow_survivors is False
    assert parser.parse_args(["calc.py", "--allow-survivors"]).allow_survivors is True


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["--scan", "--update-manifest", "--check-manifest"])
def test_allow_survivors_rejected_with_no_run_mode(mode):
    from mutate4py.__main__ import _build_parser
    from mutate4py._cli_validation import ValidationError, _validate_mutual_exclusions

    args = _build_parser().parse_args(["calc.py", mode, "--allow-survivors"])

    with pytest.raises(ValidationError) as exc:
        _validate_mutual_exclusions(args)
    assert exc.value.exit_code == 2


@pytest.mark.unit
def test_run_on_file_passes_allow_survivors(monkeypatch):
    from mutate4py.__main__ import _build_parser
    from mutate4py._dispatch import _run_on_file

    captured = {}

    def fake_run_mutations(request):
        captured["request"] = request
        return 0

    monkeypatch.setattr("mutate4py._dispatch.run_mutations", fake_run_mutations)

    args = _build_parser().parse_args(["calc.py", "--allow-survivors"])
    _run_on_file(args, "calc.py", _SRC, "/cwd")

    assert captured["request"].allow_survivors is True


_SURVIVOR_FN = "func/f"


def _recorded_function(src_path, function_id=_SURVIVOR_FN):
    from mutate4py._manifest_storage import read_sidecar_manifest

    manifest, _ = read_sidecar_manifest(src_path)
    return next(fn for fn in manifest["functions"] if fn["id"] == function_id)


@pytest.mark.component
def test_scored_run_records_survivor_in_sidecar(tmp_path):
    src_path, lcov_path, sites = _write_source_and_lcov(tmp_path)
    pytest_args = write_always_passing_pytest_project(str(tmp_path))

    assert _run(tmp_path, src_path, lcov_path, pytest_args, manifest_file=True) == 3

    fn = _recorded_function(src_path)
    assert fn["score"] == {"killed": 0, "survived": 1, "uncovered": 0}
    assert fn["survivors"] == [{"line": sites[0].line, "desc": sites[0].desc}]


@pytest.mark.component
def test_default_rerun_retries_survivor_function_and_clears_it(tmp_path):
    src_path, lcov_path, sites = _write_source_and_lcov(tmp_path)
    pytest_args = write_always_passing_pytest_project(str(tmp_path))
    assert _run(tmp_path, src_path, lcov_path, pytest_args, manifest_file=True) == 3
    assert _recorded_function(src_path)["survivors"] == [{"line": sites[0].line, "desc": sites[0].desc}]

    # The suite now kills the survivor: it fails only when the mutated text is on disk.
    # A default rerun (no --mutate-all) must retry the survivor's function.
    pytest_args = write_content_check_pytest_project(str(tmp_path), src_path, sites[0].mutant_text)
    assert _run(tmp_path, src_path, lcov_path, pytest_args, manifest_file=True) == 0

    fn = _recorded_function(src_path)
    assert fn["survivors"] == []
    assert fn["score"]["survived"] == 0


def _write_lcov_for_lines(lcov_path: str, src_path: str, lines: list[int]) -> None:
    da_lines = "\n".join(f"DA:{ln},1" for ln in lines)
    with open(lcov_path, "w") as f:
        f.write(f"SF:{src_path}\n{da_lines}\nend_of_record\n")


@pytest.mark.component
def test_default_run_without_coverage_keeps_recorded_survivor(tmp_path):
    # A default run that selects no Site (its coverage misses the survivor's line) must not
    # clear the survivor it never retested.
    src_path, lcov_path, sites = _write_source_and_lcov(tmp_path)
    pytest_args = write_always_passing_pytest_project(str(tmp_path))
    assert _run(tmp_path, src_path, lcov_path, pytest_args, manifest_file=True) == 3

    _write_lcov_for_lines(lcov_path, src_path, [])
    assert _run(tmp_path, src_path, lcov_path, pytest_args, manifest_file=True) == 0

    assert _recorded_function(src_path)["survivors"] == [{"line": sites[0].line, "desc": sites[0].desc}]
    with open(src_path) as f:
        assert check_manifest(path=src_path, source=f.read(), manifest_file=True) == 1


_TWO_SITES_IN_F = "def f(a, b):\n    x = a > b\n    return x < b\n"


@pytest.mark.component
def test_default_run_keeps_survivor_whose_line_lost_coverage(tmp_path):
    # The function stays partly covered (its second line is still covered), yet the first line's
    # survivor was never retested. The rerun must not replace the function's recorded survivors.
    src_path, lcov_path, sites = _write_source_and_lcov(tmp_path, _TWO_SITES_IN_F)
    pytest_args = write_always_passing_pytest_project(str(tmp_path))
    assert _run(tmp_path, src_path, lcov_path, pytest_args, source=_TWO_SITES_IN_F, manifest_file=True) == 3
    lost, kept = sites[0], sites[-1]

    _write_lcov_for_lines(lcov_path, src_path, [kept.line])
    assert _run(tmp_path, src_path, lcov_path, pytest_args, source=_TWO_SITES_IN_F, manifest_file=True) == 3

    assert {"line": lost.line, "desc": lost.desc} in _recorded_function(src_path)["survivors"]


@pytest.mark.component
def test_mutate_all_scores_uncovered_function(tmp_path):
    src_path, lcov_path, sites = _write_source_and_lcov(tmp_path, _TWO_FUNCTIONS)
    pytest_args = write_always_passing_pytest_project(str(tmp_path))
    assert _run(tmp_path, src_path, lcov_path, pytest_args, source=_TWO_FUNCTIONS, manifest_file=True) == 3
    assert _recorded_function(src_path, "func/g")["survivors"] != []

    f_line = next(s.line for s in sites if s.function_id == "func/f")
    _write_lcov_for_lines(lcov_path, src_path, [f_line])
    assert (
        _run(tmp_path, src_path, lcov_path, pytest_args, source=_TWO_FUNCTIONS, manifest_file=True, mutate_all=True)
        == 3
    )

    fn = _recorded_function(src_path, "func/g")
    assert fn["score"] == {"killed": 0, "survived": 0, "uncovered": 1}
    assert fn["survivors"] == []


@pytest.mark.component
def test_noop_default_run_leaves_014_sidecar_bytes(tmp_path):
    # A 0.1.4 sidecar (no score blocks) must not gain them on a default run that selects nothing.
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(_TWO_FUNCTIONS)
    lcov_path = str(tmp_path / "cov.lcov")
    _write_lcov_for_lines(lcov_path, src_path, [2])
    pytest_args = write_always_passing_pytest_project(str(tmp_path))
    assert update_manifest(path=src_path, source=_TWO_FUNCTIONS, manifest_file=True) == 0
    with open(src_path + ".manifest.json") as f:
        before = f.read()

    assert _run(tmp_path, src_path, lcov_path, pytest_args, source=_TWO_FUNCTIONS, manifest_file=True) == 0

    with open(src_path + ".manifest.json") as f:
        assert f.read() == before


@pytest.mark.unit
def test_compute_manifest_diff_includes_functions_with_survivors(tmp_path):
    from mutate4py._manifest import build_manifest
    from mutate4py._manifest_storage import ManifestLocation, write_sidecar_manifest
    from mutate4py._source_loading import _compute_manifest_diff

    src_path = str(tmp_path / "calc.py")
    manifest = build_manifest(_SRC, tested_at="2026-01-01T00:00:00Z")
    manifest["functions"][0].update(
        score={"killed": 0, "survived": 1, "uncovered": 0},
        survivors=[{"line": 2, "desc": "a > b -> a >= b"}],
        accepted=[],
    )
    write_sidecar_manifest(src_path, manifest)

    changed = _compute_manifest_diff(_SRC, ManifestLocation(path=src_path, manifest_file=True))[3]

    assert changed == {_SURVIVOR_FN}


@pytest.mark.unit
def test_finalize_source_without_scored_run_keeps_unchanged_scores(tmp_path):
    from mutate4py._manifest import build_manifest
    from mutate4py._manifest_storage import ManifestLocation
    from mutate4py._source_loading import _finalize_source

    src_path = str(tmp_path / "calc.py")
    bak_path = src_path + ".bak"
    with open(src_path, "w") as f:
        f.write(_SRC)
    existing = build_manifest(_SRC, tested_at="2020-01-01T00:00:00Z")
    survivors = [{"line": 2, "desc": "a > b -> a >= b"}]
    existing["functions"][0].update(
        score={"killed": 0, "survived": 1, "uncovered": 0}, survivors=survivors, accepted=[]
    )

    _finalize_source(
        _SRC,
        "2026-01-01T00:00:00Z",
        bak_path,
        ManifestLocation(path=src_path, manifest_file=True),
        existing_manifest=existing,
    )

    fn = _recorded_function(src_path)
    assert fn["score"] == {"killed": 0, "survived": 1, "uncovered": 0}
    assert fn["survivors"] == survivors


_MARKED = "def f(a, b):\n    return a > b  # mutate4py: equivalent same for all inputs\n"
_UNMARKED = "def f(a, b):\n    return a > b\n"


@pytest.mark.component
def test_default_rerun_retests_function_whose_marker_was_removed(tmp_path):
    src_path, lcov_path, sites = _write_source_and_lcov(tmp_path, _MARKED)
    pytest_args = write_always_passing_pytest_project(str(tmp_path))
    assert _run(tmp_path, src_path, lcov_path, pytest_args, source=_MARKED, manifest_file=True) == 0
    assert _recorded_function(src_path)["accepted"] == [
        {"line": sites[0].line, "desc": sites[0].desc, "reason": "same for all inputs"}
    ]

    # The reviewer rejects the claim: the developer deletes the marker and nothing else changes.
    src_path, lcov_path, _ = _write_source_and_lcov(tmp_path, _UNMARKED)
    assert _run(tmp_path, src_path, lcov_path, pytest_args, source=_UNMARKED, manifest_file=True) == 3

    assert _recorded_function(src_path)["accepted"] == []
