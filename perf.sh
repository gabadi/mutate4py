#!/usr/bin/env bash
# Times every quality check this project runs (mirrors check.sh) plus a real,
# full-src/ mutation-testing run using per-mutant test selection, and prints a
# duration table with a total. Mirrors mutate4js's scripts/perf-checks.ts.
#
# Unlike check.sh (which mutates only a sample file for a fast CI-friendly
# signal), this dogfoods mutate4py against the entire src/ directory, so it
# is expected to take minutes, not seconds. Run it to benchmark real
# mutation-testing cost, not as a pre-commit gate.
#
# Usage: ./perf.sh
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"
PERF_LOG="$(mktemp)"
trap 'rm -f "$PERF_LOG"' EXIT

declare -a NAMES
declare -a DURATIONS
declare -a STATUSES

_run() {
    local name="$1"; shift
    local start=$SECONDS
    local status="ok"
    if ! "$@" >"$PERF_LOG" 2>&1; then
        status="FAILED"
    fi
    local elapsed=$((SECONDS - start))
    NAMES+=("$name")
    DURATIONS+=("${elapsed}s")
    STATUSES+=("$status")
    if [[ "$status" == "FAILED" ]]; then
        echo ""
        echo "--- failure output: $name ---"
        tail -20 "$PERF_LOG"
    fi
}

# ── Static analysis ────────────────────────────────────────────────────────────
_run "lint"            uv run ruff check src/ tests/
_run "format"          uv run ruff format --check src/ tests/

# ── Tests + coverage (with per-test contexts for mutation test selection) ─────
_run "test"            uv run pytest --cov --cov-context=test \
                           --cov-report=lcov:lcov.info --cov-report=term-missing \
                           --cov-fail-under=90 -q

# ── Quality gates (need lcov.info from the test run) ───────────────────────────
_run "crap"            uv run crap4py src/ --lcov lcov.info --max-crap 6
DRYWALL="${DRYWALL:-$(command -v drywall 2>/dev/null || echo "$HOME/.local/bin/drywall")}"
_run "dry"             "$DRYWALL" src/
_run "check-manifest"  uv run mutate4py src/ --check-manifest

_run "acceptance"      bash acceptance/run_acceptance.sh

# ── Mutation testing: dogfood mutate4py against the whole src/ directory,
# using --test-contexts (built from the coverage run above) so each mutant
# only re-runs the tests that actually cover it, instead of the full suite.
# --mutate-all forces every covered site to run (not just the differential
# fast-path), so the number reflects real mutation-execution cost.
_run "mutation (src/, --test-contexts)" \
    uv run mutate4py src/ --lcov lcov.info --test-contexts .coverage \
        --mutate-all --mutation-warning 100000

# ── Summary ────────────────────────────────────────────────────────────────────
name_width=0
for n in "${NAMES[@]}"; do
    (( ${#n} > name_width )) && name_width=${#n}
done

echo ""
printf "%-${name_width}s  %8s   %s\n" "check" "duration" "status"
printf '%.0s-' $(seq 1 $((name_width + 22))); echo ""

total=0
for i in "${!NAMES[@]}"; do
    printf "%-${name_width}s  %8s   %s\n" "${NAMES[$i]}" "${DURATIONS[$i]}" "${STATUSES[$i]}"
    total=$((total + ${DURATIONS[$i]%s}))
done

printf '%.0s-' $(seq 1 $((name_width + 22))); echo ""
printf "%-${name_width}s  %7ss\n" "total" "$total"

for status in "${STATUSES[@]}"; do
    [[ "$status" == "FAILED" ]] && exit 1
done
exit 0
