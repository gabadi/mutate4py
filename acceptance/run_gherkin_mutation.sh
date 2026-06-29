#!/usr/bin/env bash
# Run gherkin-mutator for all feature files in parallel (one process per feature).
# Requires: gherkin-parser, gherkin-mutator, runner_adapter.py executable.
# Usage: ./acceptance/run_gherkin_mutation.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PARSED_DIR="$REPO_ROOT/acceptance/parsed"
GENERATED_DIR="$REPO_ROOT/acceptance/generated"
LOG_DIR="$(mktemp -d)"

mkdir -p "$PARSED_DIR" "$GENERATED_DIR"
chmod +x "$REPO_ROOT/acceptance/runner_adapter.py"

declare -A STEPS_MAP
STEPS_MAP[site-discovery]="site_discovery_steps"
STEPS_MAP[manifest]="manifest_steps"
STEPS_MAP[coverage]="coverage_steps"
STEPS_MAP[run-loop]="run_loop_steps"
STEPS_MAP[cli-surface]="cli_surface_steps"
STEPS_MAP[parallel-workers]="parallel_workers_steps"

# Regenerate acceptance entrypoints before mutation (stale entrypoints cause all mutations to error)
echo "=== Regenerating acceptance entrypoints ==="
for stem in "${!STEPS_MAP[@]}"; do
    steps_mod="${STEPS_MAP[$stem]}"
    parsed="$PARSED_DIR/${stem}_parsed.json"
    gherkin-parser "$REPO_ROOT/features/${stem}.feature" "$parsed"
    uv run python "$REPO_ROOT/acceptance/generate_acceptance.py" \
        "$parsed" "$steps_mod" "$GENERATED_DIR" "features/${stem}.feature" > /dev/null
done

echo ""
echo "=== Gherkin mutation (parallel by feature) ==="

pids=()
ordered_stems=()

for stem in "${!STEPS_MAP[@]}"; do
    log="$LOG_DIR/${stem}.log"
    gherkin-mutator \
        --feature "$REPO_ROOT/features/${stem}.feature" \
        --generated-dir "$GENERATED_DIR" \
        --runner-worker "$REPO_ROOT/acceptance/runner_adapter.py" \
        --workers 4 > "$log" 2>&1 &
    pids+=($!)
    ordered_stems+=("$stem")
    echo "  started: $stem (pid $!)"
done

echo ""
FAILED=0
for i in "${!pids[@]}"; do
    pid="${pids[$i]}"
    stem="${ordered_stems[$i]}"
    if wait "$pid"; then
        echo "PASS: $stem"
    else
        echo "FAIL: $stem"
        cat "$LOG_DIR/${stem}.log"
        FAILED=$((FAILED + 1))
    fi
done

rm -rf "$LOG_DIR"

echo ""
if [[ $FAILED -gt 0 ]]; then
    echo "Gherkin mutation: $FAILED feature(s) had survivors"
    exit 1
fi
echo "Gherkin mutation: all features passed"
