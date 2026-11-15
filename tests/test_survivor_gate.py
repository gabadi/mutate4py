"""Survivor gate (#76): a scored run with an unaccepted survivor exits 3.

Component tests drive run_mutations in-process with real pytest subprocesses.
Each run is handed the Measurement the test states (see `_measurement_helpers`),
so a test controls which lines the suite reached without a coverage file.
Unit tests cover the --allow-survivors flag, its rejection in no-run modes,
and its wiring from the CLI namespace into the run request.
"""

import io
import json
import os
from contextlib import redirect_stdout

import pytest

from ._measurement_helpers import measurement_for
from ._pytest_project_helpers import (
    write_always_passing_pytest_project,
    write_content_check_pytest_project,
    write_sleep_if_mutated_pytest_project,
)
from mutate4py._discovery import discover_sites
from mutate4py._runner import RunMutationsRequest, check_manifest, run_mutations, update_manifest

_SRC = "def f(a, b):\n    return a > b\n"
_TWO_FUNCTIONS = "def f(a, b):\n    return a > b\n\n\ndef g(a, b):\n    return a > b\n"


def _write_source(tmp_path, source=_SRC):
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(source)
    return src_path, discover_sites(source)


def _covering(src_path, lines):
    """A Measurement in which the suite reached `lines` at import time (Empty context)."""
    return measurement_for(os.path.abspath(src_path), {"": lines}, wall=0.01)


def _covering_all(src_path, sites):
    return _covering(src_path, [s.line for s in sites])


def _request(tmp_path, src_path, measurement, pytest_args, **extra):
    return RunMutationsRequest(
        path=src_path,
        source=extra.pop("source", _SRC),
        measurement=measurement,
        pytest_args=pytest_args,
        timeout_factor=extra.pop("timeout_factor", 10),
        # A fake Measurement carries no test durations, so the timeout is this floor alone.
        # The full-set confirmation runs a real pytest subprocess (about 1s), so the floor
        # must clear its startup or the confirmation times out and reads as a kill.
        min_timeout=extra.pop("min_timeout", 5.0),
        warning_threshold=1000,
        cwd=str(tmp_path),
        **extra,
    )


def _run(tmp_path, src_path, measurement, pytest_args, **extra):
    request = _request(tmp_path, src_path, measurement, pytest_args, **extra)
    with redirect_stdout(io.StringIO()):
        return run_mutations(request)


@pytest.mark.component
def test_run_mutations_returns_3_when_a_mutant_survives(tmp_path):
    src_path, sites = _write_source(tmp_path)
    pytest_args = write_always_passing_pytest_project(str(tmp_path))

    assert _run(tmp_path, src_path, _covering_all(src_path, sites), pytest_args) == 3


@pytest.mark.component
def test_run_mutations_returns_0_when_survivors_allowed(tmp_path):
    src_path, sites = _write_source(tmp_path)
    pytest_args = write_always_passing_pytest_project(str(tmp_path))

    assert _run(tmp_path, src_path, _covering_all(src_path, sites), pytest_args, allow_survivors=True) == 0


@pytest.mark.component
def test_run_mutations_timeout_is_not_a_survivor(tmp_path):
    # A mutant that exceeds the timeout is Killed, so the run exits 0.
    # A fast pass would be a survivor and exit 3, so 0 proves the timeout path.
    src_path, sites = _write_source(tmp_path)
    pytest_args = write_sleep_if_mutated_pytest_project(str(tmp_path), src_path, sites[0].mutant_text, 5)

    measurement = _covering_all(src_path, sites)
    assert _run(tmp_path, src_path, measurement, pytest_args, timeout_factor=1, min_timeout=0.1) == 0


@pytest.mark.component
def test_run_mutations_exits_0_when_every_survivor_is_accepted(tmp_path):
    # The marker accepts the survivor, so the run does not exit 3 and the reason is recorded.
    marked = "def f(a, b):\n    return a > b  # mutate4py: equivalent same for all inputs\n"
    src_path, sites = _write_source(tmp_path, marked)
    pytest_args = write_always_passing_pytest_project(str(tmp_path))

    code = _run(tmp_path, src_path, _covering_all(src_path, sites), pytest_args, source=marked, manifest_file=True)
    assert code == 0

    fn = _recorded_function(src_path)
    assert fn["survivors"] == []
    assert fn["accepted"][0]["reason"] == "same for all inputs"


@pytest.mark.component
def test_empty_marker_reason_returns_2_before_baseline(tmp_path):
    # An empty reason is a usage error, raised before any .bak is written or the source is touched.
    bare = "def f(a, b):\n    return a > b  # mutate4py: equivalent\n"
    src_path, sites = _write_source(tmp_path, bare)
    pytest_args = write_always_passing_pytest_project(str(tmp_path))
    request = _request(tmp_path, src_path, _covering_all(src_path, sites), pytest_args, source=bare)

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
    src_path, sites = _write_source(tmp_path)
    pytest_args = write_always_passing_pytest_project(str(tmp_path))

    assert _run(tmp_path, src_path, _covering_all(src_path, sites), pytest_args, manifest_file=True) == 3

    fn = _recorded_function(src_path)
    assert fn["score"] == {"killed": 0, "survived": 1, "uncovered": 0}
    assert fn["survivors"] == [{"line": sites[0].line, "desc": sites[0].desc}]


@pytest.mark.component
def test_default_rerun_retries_survivor_function_once_its_tests_change_and_clears_it(tmp_path):
    src_path, sites = _write_source(tmp_path)
    # The Measurement names the content-check test as reaching the function, so the digest
    # reads that file. Its content is the only thing that changes between the two runs.
    context = "tests/test_content_check.py::test_not_mutated"
    measurement = measurement_for(os.path.abspath(src_path), {context: [s.line for s in sites]}, wall=0.01)
    pytest_args = write_content_check_pytest_project(str(tmp_path), src_path, "NEVER_PRESENT_IN_THE_SOURCE")
    assert _run(tmp_path, src_path, measurement, pytest_args, manifest_file=True) == 3
    assert _recorded_function(src_path)["survivors"] == [{"line": sites[0].line, "desc": sites[0].desc}]

    # The suite now kills the survivor: it fails only when the mutated text is on disk.
    # The edit moves the stored tests digest, so the function is re-scored and the survivor clears.
    pytest_args = write_content_check_pytest_project(str(tmp_path), src_path, sites[0].mutant_text)
    assert _run(tmp_path, src_path, measurement, pytest_args, manifest_file=True) == 0

    fn = _recorded_function(src_path)
    assert fn["survivors"] == []
    assert fn["score"]["survived"] == 0


@pytest.mark.component
def test_default_run_without_coverage_keeps_recorded_survivor(tmp_path):
    # A default run that selects no Site (its coverage misses the survivor's line) must not
    # clear the survivor it never retested. The skipped function's recorded survivor still
    # counts toward the exit code (spec 89 §5), so the run exits 3.
    src_path, sites = _write_source(tmp_path)
    pytest_args = write_always_passing_pytest_project(str(tmp_path))
    assert _run(tmp_path, src_path, _covering_all(src_path, sites), pytest_args, manifest_file=True) == 3

    assert _run(tmp_path, src_path, _covering(src_path, []), pytest_args, manifest_file=True) == 3

    assert _recorded_function(src_path)["survivors"] == [{"line": sites[0].line, "desc": sites[0].desc}]
    with open(src_path) as f:
        assert check_manifest(path=src_path, source=f.read(), manifest_file=True) == 1


_TWO_SITES_IN_F = "def f(a, b):\n    x = a > b\n    return x < b\n"


@pytest.mark.component
def test_default_run_keeps_survivor_whose_line_lost_coverage(tmp_path):
    # The function stays partly covered (its second line is still covered), yet the first line's
    # survivor was never retested. The rerun must not replace the function's recorded survivors.
    src_path, sites = _write_source(tmp_path, _TWO_SITES_IN_F)
    pytest_args = write_always_passing_pytest_project(str(tmp_path))
    run = dict(source=_TWO_SITES_IN_F, manifest_file=True)
    assert _run(tmp_path, src_path, _covering_all(src_path, sites), pytest_args, **run) == 3
    lost, kept = sites[0], sites[-1]

    assert _run(tmp_path, src_path, _covering(src_path, [kept.line]), pytest_args, **run) == 3

    assert {"line": lost.line, "desc": lost.desc} in _recorded_function(src_path)["survivors"]


@pytest.mark.component
def test_default_run_scores_every_function_of_a_014_sidecar(tmp_path):
    # A 0.1.4 sidecar carries no score blocks, so every function is Unscored and a default run scores
    # all of them (ADR 0029 rule 1). g's Site is not covered, yet g is scored uncovered, not skipped:
    # a skipped Unscored function would keep the Manifest from ever taking the no-change skip.
    src_path = str(tmp_path / "calc.py")
    with open(src_path, "w") as f:
        f.write(_TWO_FUNCTIONS)
    pytest_args = write_always_passing_pytest_project(str(tmp_path))
    assert update_manifest(path=src_path, source=_TWO_FUNCTIONS, manifest_file=True) == 0

    measurement = _covering(src_path, [2])
    assert _run(tmp_path, src_path, measurement, pytest_args, source=_TWO_FUNCTIONS, manifest_file=True) == 3

    with open(src_path + ".manifest.json") as f:
        after = json.load(f)
    assert all("score" in fn for fn in after["functions"])
    assert _recorded_function(src_path)["score"] == {"killed": 0, "survived": 1, "uncovered": 0}
    assert _recorded_function(src_path, "func/g")["score"] == {"killed": 0, "survived": 0, "uncovered": 1}
    assert after.get("tests_fingerprint") is not None


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

    changed = _compute_manifest_diff(_SRC, ManifestLocation(path=src_path, manifest_file=True)).changed_fn_ids

    assert changed == {_SURVIVOR_FN}


@pytest.mark.unit
def test_compute_manifest_diff_includes_functions_without_a_score_block(tmp_path):
    # Source and tests are unchanged, but the stored entry carries no score block: the function is Unscored
    # and a default run selects it (ADR 0029 rule 1).
    from mutate4py._manifest import build_manifest
    from mutate4py._manifest_storage import ManifestLocation, write_sidecar_manifest
    from mutate4py._source_loading import _compute_manifest_diff

    src_path = str(tmp_path / "calc.py")
    write_sidecar_manifest(src_path, build_manifest(_SRC, tested_at="2026-01-01T00:00:00Z"))

    changed = _compute_manifest_diff(_SRC, ManifestLocation(path=src_path, manifest_file=True)).changed_fn_ids

    assert changed == {_SURVIVOR_FN}


@pytest.mark.unit
def test_compute_manifest_diff_leaves_out_a_scored_function_without_survivors(tmp_path):
    from mutate4py._manifest import build_manifest
    from mutate4py._manifest_storage import ManifestLocation, write_sidecar_manifest
    from mutate4py._source_loading import _compute_manifest_diff

    src_path = str(tmp_path / "calc.py")
    manifest = build_manifest(_SRC, tested_at="2026-01-01T00:00:00Z")
    manifest["functions"][0].update(score={"killed": 1, "survived": 0, "uncovered": 0}, survivors=[], accepted=[])
    write_sidecar_manifest(src_path, manifest)

    changed = _compute_manifest_diff(_SRC, ManifestLocation(path=src_path, manifest_file=True)).changed_fn_ids

    assert changed == set()


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
    src_path, sites = _write_source(tmp_path, _MARKED)
    pytest_args = write_always_passing_pytest_project(str(tmp_path))
    assert (
        _run(tmp_path, src_path, _covering_all(src_path, sites), pytest_args, source=_MARKED, manifest_file=True) == 0
    )
    assert _recorded_function(src_path)["accepted"] == [
        {"line": sites[0].line, "desc": sites[0].desc, "reason": "same for all inputs"}
    ]

    # The reviewer rejects the claim: the developer deletes the marker and nothing else changes.
    src_path, sites = _write_source(tmp_path, _UNMARKED)
    assert (
        _run(tmp_path, src_path, _covering_all(src_path, sites), pytest_args, source=_UNMARKED, manifest_file=True) == 3
    )

    assert _recorded_function(src_path)["accepted"] == []


# --- Survivor confirmation (#97) ---------------------------------------------

# A memoised body: test_a's call runs the body and caches the result, so test_b reads the
# cache and never reaches the body. The Measurement therefore names test_a alone for the
# body's lines: a narrowed run of a body Mutant passes, and only the full set (test_b, reading
# the cache the Mutant wrote) kills it. f(2) is 7, so no body Mutant matches the expected value.
_MEMOISED = "_cache = {}\n\n\ndef f(a):\n    if a not in _cache:\n        _cache[a] = a * 3 + 1\n    return _cache[a]\n"


def _write_memoised_project(tmp_path) -> list[str]:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "test_a_first_call.py").write_text(
        "from calc import f\n\n\ndef test_first_call_is_positive():\n    assert f(2) > 0\n"
    )
    (tests_dir / "test_b_cached_call.py").write_text(
        "from calc import f\n\n\ndef test_cached_call_is_seven():\n    assert f(2) == 7\n"
    )
    return ["-q", "tests"]


@pytest.mark.component
def test_memoised_body_survivor_is_confirmed_killed_by_the_full_set(tmp_path):
    # The narrowed run of a body Mutant names test_a alone and passes. The full set kills it,
    # so the Mutant is a confirmation kill and the run has no unaccepted Survivor.
    src_path, _ = _write_source(tmp_path, _MEMOISED)
    pytest_args = _write_memoised_project(tmp_path)
    body_lines = [5, 6, 7]
    measurement = measurement_for(
        os.path.abspath(src_path),
        {"tests/test_a_first_call.py::test_first_call_is_positive": body_lines},
        wall=0.01,
    )

    assert _run(tmp_path, src_path, measurement, pytest_args, source=_MEMOISED, manifest_file=True) == 0

    fn = _recorded_function(src_path)
    assert fn["survivors"] == []
    assert fn["score"]["survived"] == 0
