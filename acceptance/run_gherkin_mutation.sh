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
echo "=== Gherkin mutation (parallel by feature, batched) ==="

# Running all features concurrently at a fixed --workers 4 each oversubscribes
# the CPU (e.g. 6 features * 4 workers = 24 threads on a 10-core box), causing
# spurious subprocess timeouts under contention rather than real mutation
# survivors. Keep --workers 4 per feature (unchanged, already tuned) but cap
# how many features run at once so total concurrent worker threads stays near
# the machine's core count.
WORKERS_PER_FEATURE=4
NPROC="$(getconf _NPROCESSORS_ONLN 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)"
BATCH_SIZE=$(( NPROC / WORKERS_PER_FEATURE ))
if [[ $BATCH_SIZE -lt 1 ]]; then
    BATCH_SIZE=1
fi
echo "  cores: $NPROC, workers/feature: $WORKERS_PER_FEATURE, concurrent features/batch: $BATCH_SIZE"

all_stems=("${!STEPS_MAP[@]}")
FAILED=0

for ((batch_start=0; batch_start<${#all_stems[@]}; batch_start+=BATCH_SIZE)); do
    pids=()
    ordered_stems=()
    for ((i=batch_start; i<batch_start+BATCH_SIZE && i<${#all_stems[@]}; i++)); do
        stem="${all_stems[$i]}"
        log="$LOG_DIR/${stem}.log"
        gherkin-mutator \
            --feature "$REPO_ROOT/features/${stem}.feature" \
            --generated-dir "$GENERATED_DIR" \
            --runner-worker "$REPO_ROOT/acceptance/runner_adapter.py" \
            --workers "$WORKERS_PER_FEATURE" > "$log" 2>&1 &
        pids+=($!)
        ordered_stems+=("$stem")
        echo "  started: $stem (pid $!)"
    done

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
done

rm -rf "$LOG_DIR"

echo ""
if [[ $FAILED -gt 0 ]]; then
    echo "Gherkin mutation: $FAILED feature(s) had survivors"
    exit 1
fi
echo "Gherkin mutation: all features passed"
