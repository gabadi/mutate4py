#!/usr/bin/env bash
# Run acceptance tests for all feature files.
# Usage: ./acceptance/run_acceptance.sh
set -euo pipefail

# Without gherkin-parser, generation used to be skipped silently and the stale
# acceptance/generated/*.py ran instead (#83). Fail before anything runs.
if ! command -v gherkin-parser &>/dev/null; then
    echo "  ✗ gherkin-parser not found on PATH — run 'just install-tools' (it builds the CI-pinned version into ~/.local/bin)" >&2
    exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PARSED_DIR="$REPO_ROOT/acceptance/parsed"
GENERATED_DIR="$REPO_ROOT/acceptance/generated"

mkdir -p "$PARSED_DIR" "$GENERATED_DIR"

declare -A STEPS_MAP
STEPS_MAP[site-discovery]="site_discovery_steps"
STEPS_MAP[manifest]="manifest_steps"
STEPS_MAP[coverage]="coverage_steps"
STEPS_MAP[run-loop]="run_loop_steps"
STEPS_MAP[cli-surface]="cli_surface_steps"
STEPS_MAP[parallel-workers]="parallel_workers_steps"
STEPS_MAP[test-selection]="test_selection_steps"
STEPS_MAP[tests-digest]="tests_digest_steps"

# Feature files intentionally NOT wired to a steps module. Each entry must
# carry a reason — this is the debt register for the "no silent skip" gate
# (issue #38 gate 04): an unwired feature file with no entry here is a hard
# error, not a silent skip.
declare -A OPT_OUT
OPT_OUT[ci]="documents external CI/CD infrastructure (GitHub Actions job semantics, tag-triggered release/publish) that this local step-execution harness cannot run or simulate; see the feature's header for the F1 design-intent contract it records. KNOWN STALE: ci-3 claims the crap/mutation gates don't run — CI has since grown a CRAP step and a manifest-check step; the full mutate-all scan is still opt-in only. Kept as historical record, not a live spec."

# A stem in both a steps map and its opt-out list is itself a silent-skip
# hole: the opt-out branch would win, so a feature with a real steps module
# would quietly stop running the moment someone (mis)added an opt-out entry
# for it. Refuse to start rather than let that combination stand.
check_no_overlap() {
    local -n steps_map=$1
    local -n opt_out=$2
    local label=$3
    local stem
    for stem in "${!opt_out[@]}"; do
        if [[ -n "${steps_map[$stem]:-}" ]]; then
            echo "  ✗ $label: '$stem' is in both the steps map and the opt-out list — pick one" >&2
            return 1
        fi
    done
    return 0
}
check_no_overlap STEPS_MAP OPT_OUT "feature" || exit 1

# Generation pass: parse + codegen every feature file in $2 that isn't
# opted out, via the steps map in $1. Prints "OPTED-OUT: <stem> (<reason>)"
# for opt-outs and a "✗ ... has no steps module" error (returning 1) for
# anything wired to neither — an unwired feature file is a hard error naming
# the file, not a silent skip (issue #38 gate 04).
generate_pass() {
    local -n steps_map=$1
    local -n opt_out=$2
    local label=$3
    shift 3
    local unwired=0
    local feature_file stem steps_mod parsed rel_feature
    for feature_file in "$@"; do
        [[ -f "$feature_file" ]] || continue
        stem="$(basename "$feature_file" .feature)"
        if [[ -n "${opt_out[$stem]:-}" ]]; then
            echo "OPTED-OUT: $stem (${opt_out[$stem]})"
            continue
        fi
        if [[ -z "${steps_map[$stem]:-}" ]]; then
            echo "  ✗ $feature_file has no steps module and is not on the $label opt-out list" >&2
            unwired=1
            continue
        fi
        steps_mod="${steps_map[$stem]}"
        parsed="$PARSED_DIR/${stem}_parsed.json"
        rel_feature="features/${stem}.feature"
        gherkin-parser "$feature_file" "$parsed" || { echo "  ✗ gherkin-parser failed on $feature_file" >&2; return 1; }
        uv run python "$REPO_ROOT/acceptance/generate_acceptance.py" \
            "$parsed" "$steps_mod" "$GENERATED_DIR" "$rel_feature" || { echo "  ✗ codegen failed for $stem" >&2; return 1; }
    done
    return "$unwired"
}

# ── Acceptance suite ──────────────────────────────────────────────────────────

declare -a features=("$REPO_ROOT"/features/*.feature)
generate_pass STEPS_MAP OPT_OUT "OPT_OUT" "${features[@]}" || {
    echo "  ✗ one or more feature files are unwired — add a steps module or an OPT_OUT entry" >&2
    exit 1
}

# Execution pass (parallel)
declare -a pids=()
declare -a names=()
declare -a tmpouts=()

for feature_file in "${features[@]}"; do
    stem="$(basename "$feature_file" .feature)"
    [[ -n "${OPT_OUT[$stem]:-}" ]] && continue
    generated="$GENERATED_DIR/${stem}_acceptance.py"
    tmpout="$(mktemp)"
    uv run python "$generated" >"$tmpout" 2>&1 &
    pids+=($!)
    names+=("$stem")
    tmpouts+=("$tmpout")
done

FAILED=0
PASSED=0
for i in "${!pids[@]}"; do
    if wait "${pids[$i]}"; then
        echo "PASS ${names[$i]}"
        PASSED=$((PASSED + 1))
    else
        echo "FAIL ${names[$i]}"
        cat "${tmpouts[$i]}"
        FAILED=$((FAILED + 1))
    fi
    rm -f "${tmpouts[$i]}"
done

echo ""
echo "=== Acceptance summary: $PASSED feature(s) passed, $FAILED failed ==="

if [[ $FAILED -gt 0 ]]; then
    echo "Skipping Gherkin mutation — acceptance tests failed"
    exit 1
fi

exit 0
