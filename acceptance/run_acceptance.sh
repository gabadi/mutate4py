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

FAILED=0
PASSED=0

for feature_file in "$REPO_ROOT"/features/*.feature; do
    stem="$(basename "$feature_file" .feature)"

    if [[ "$stem" == *_qa ]]; then
        continue
    fi

    steps_mod="${STEPS_MAP[$stem]:-}"
    if [[ -z "$steps_mod" ]]; then
        echo "SKIP: no steps module for $stem"
        continue
    fi

    echo "=== $stem ==="

    parsed="$PARSED_DIR/${stem}_parsed.json"
    gherkin-parser "$feature_file" "$parsed"

    rel_feature="features/${stem}.feature"
    uv run python "$REPO_ROOT/acceptance/generate_acceptance.py" \
        "$parsed" "$steps_mod" "$GENERATED_DIR" "$rel_feature"

    generated="$GENERATED_DIR/${stem}_acceptance.py"
    if uv run python "$generated"; then
        PASSED=$((PASSED + 1))
    else
        FAILED=$((FAILED + 1))
    fi
done

echo ""
echo "=== Acceptance summary: $PASSED feature(s) passed, $FAILED failed ==="

if [[ $FAILED -gt 0 ]]; then
    echo "Skipping Gherkin mutation — acceptance tests failed"
    exit 1
fi

echo ""
echo "=== QA end-to-end suite ==="

QA_FAILED=0
QA_PASSED=0

for feature_file in "$REPO_ROOT"/features/*_qa.feature; do
    [[ -f "$feature_file" ]] || continue
    stem="$(basename "$feature_file" .feature)"
    steps_mod="${QA_STEPS_MAP[$stem]:-}"
    if [[ -z "$steps_mod" ]]; then
        echo "SKIP QA: no steps module for $stem"
        continue
    fi

    echo "=== QA: $stem ==="

    parsed="$PARSED_DIR/${stem}_parsed.json"
    gherkin-parser "$feature_file" "$parsed"

    rel_feature="features/${stem}.feature"
    uv run python "$REPO_ROOT/acceptance/generate_acceptance.py" \
        "$parsed" "$steps_mod" "$GENERATED_DIR" "$rel_feature"

    generated="$GENERATED_DIR/${stem}_acceptance.py"
    if uv run python "$generated"; then
        QA_PASSED=$((QA_PASSED + 1))
    else
        QA_FAILED=$((QA_FAILED + 1))
    fi
done

echo ""
echo "=== QA suite: $QA_PASSED feature(s) passed, $QA_FAILED failed ==="

if [[ $QA_FAILED -gt 0 ]]; then
    exit 1
fi

exit 0
