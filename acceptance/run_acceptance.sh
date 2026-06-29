#!/usr/bin/env bash
# Run acceptance tests for all feature files.
# Usage: ./acceptance/run_acceptance.sh
set -euo pipefail

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

declare -A QA_STEPS_MAP
QA_STEPS_MAP[site-discovery_qa]="site_discovery_qa_steps"
QA_STEPS_MAP[manifest_qa]="manifest_qa_steps"
QA_STEPS_MAP[coverage_qa]="coverage_qa_steps"
QA_STEPS_MAP[run-loop_qa]="run_loop_qa_steps"
QA_STEPS_MAP[cli-surface_qa]="cli_surface_qa_steps"
QA_STEPS_MAP[parallel-workers_qa]="parallel_workers_qa_steps"

# ── Non-QA suite ──────────────────────────────────────────────────────────────

# Generation pass (sequential — shared GENERATED_DIR)
for feature_file in "$REPO_ROOT"/features/*.feature; do
    stem="$(basename "$feature_file" .feature)"
    [[ "$stem" == *_qa ]] && continue
    [[ -z "${STEPS_MAP[$stem]:-}" ]] && continue
    steps_mod="${STEPS_MAP[$stem]}"
    parsed="$PARSED_DIR/${stem}_parsed.json"
    rel_feature="features/${stem}.feature"
    if command -v gherkin-parser &>/dev/null; then
        gherkin-parser "$feature_file" "$parsed"
        uv run python "$REPO_ROOT/acceptance/generate_acceptance.py" \
            "$parsed" "$steps_mod" "$GENERATED_DIR" "$rel_feature"
    fi
done

# Execution pass (parallel)
declare -a pids=()
declare -a names=()
declare -a tmpouts=()

for feature_file in "$REPO_ROOT"/features/*.feature; do
    stem="$(basename "$feature_file" .feature)"
    [[ "$stem" == *_qa ]] && continue
    [[ -z "${STEPS_MAP[$stem]:-}" ]] && { echo "SKIP: no steps module for $stem"; continue; }
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

# ── QA end-to-end suite ───────────────────────────────────────────────────────

echo ""
echo "=== QA end-to-end suite ==="

# Generation pass (sequential)
for feature_file in "$REPO_ROOT"/features/*_qa.feature; do
    [[ -f "$feature_file" ]] || continue
    stem="$(basename "$feature_file" .feature)"
    [[ -z "${QA_STEPS_MAP[$stem]:-}" ]] && continue
    steps_mod="${QA_STEPS_MAP[$stem]}"
    parsed="$PARSED_DIR/${stem}_parsed.json"
    rel_feature="features/${stem}.feature"
    if command -v gherkin-parser &>/dev/null; then
        gherkin-parser "$feature_file" "$parsed"
        uv run python "$REPO_ROOT/acceptance/generate_acceptance.py" \
            "$parsed" "$steps_mod" "$GENERATED_DIR" "$rel_feature"
    fi
done

# Execution pass (parallel)
declare -a qa_pids=()
declare -a qa_names=()
declare -a qa_tmpouts=()

for feature_file in "$REPO_ROOT"/features/*_qa.feature; do
    [[ -f "$feature_file" ]] || continue
    stem="$(basename "$feature_file" .feature)"
    [[ -z "${QA_STEPS_MAP[$stem]:-}" ]] && { echo "SKIP QA: no steps module for $stem"; continue; }
    generated="$GENERATED_DIR/${stem}_acceptance.py"
    tmpout="$(mktemp)"
    uv run python "$generated" >"$tmpout" 2>&1 &
    qa_pids+=($!)
    qa_names+=("$stem")
    qa_tmpouts+=("$tmpout")
done

QA_FAILED=0
QA_PASSED=0
for i in "${!qa_pids[@]}"; do
    if wait "${qa_pids[$i]}"; then
        echo "PASS ${qa_names[$i]}"
        QA_PASSED=$((QA_PASSED + 1))
    else
        echo "FAIL ${qa_names[$i]}"
        cat "${qa_tmpouts[$i]}"
        QA_FAILED=$((QA_FAILED + 1))
    fi
    rm -f "${qa_tmpouts[$i]}"
done

echo ""
echo "=== QA suite: $QA_PASSED feature(s) passed, $QA_FAILED failed ==="

if [[ $QA_FAILED -gt 0 ]]; then
    exit 1
fi

exit 0
