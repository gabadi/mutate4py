#!/usr/bin/env bash
# Quality gate timing check — runs all gates and reports elapsed time for each.
# Usage: ./check.sh [--skip-gherkin-mutation]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
SKIP_GHERKIN_MUTATION=0
[[ "${1:-}" == "--skip-gherkin-mutation" ]] && SKIP_GHERKIN_MUTATION=1

declare -a GATE_NAMES
declare -a GATE_TIMES
declare -a GATE_STATUS

_run_gate() {
    local name="$1"; shift
    echo ""
    echo "━━━ $name ━━━"
    local start=$SECONDS
    local status="PASS"
    if ! "$@" ; then
        status="FAIL"
    fi
    local elapsed=$((SECONDS - start))
    GATE_NAMES+=("$name")
    GATE_TIMES+=("${elapsed}s")
    GATE_STATUS+=("$status")
}

cd "$REPO_ROOT"

# ── Static analysis ────────────────────────────────────────────────────────────
_run_gate "Lint"          uv run ruff check src/ tests/
_run_gate "Format"        uv run ruff format --check src/ tests/

# ── Tests + coverage ───────────────────────────────────────────────────────────
_run_gate "Tests"         uv run pytest --cov --cov-report=lcov:lcov.info \
                              --cov-report=term-missing --cov-fail-under=90 -q

# ── Quality gates (need lcov.info from Tests) ──────────────────────────────────
_run_gate "CRAP"          uv run crap4py src/ --lcov lcov.info --max-crap 6
DRYWALL="${DRYWALL:-$(command -v drywall 2>/dev/null || echo "$HOME/.local/bin/drywall")}"
_run_gate "DRY"           "$DRYWALL" src/
_run_gate "Manifest"      uv run mutate4py src/ --check-manifest

# ── Mutation run (sample: _cmd.py with full test suite) ───────────────────────
echo ""
echo "━━━ Mutations (_cmd.py sample, full test suite) ━━━"
echo "  Note: full src/ scales linearly per file × test suite duration"
mut_start=$SECONDS
mut_status="PASS"
if ! uv run mutate4py src/mutate4py/_cmd.py --lcov lcov.info --mutate-all; then
    mut_status="FAIL"
fi
mut_elapsed=$((SECONDS - mut_start))
GATE_NAMES+=("Mutations (sample)")
GATE_TIMES+=("${mut_elapsed}s")
GATE_STATUS+=("$mut_status")

# ── Acceptance tests ───────────────────────────────────────────────────────────
_run_gate "Acceptance"    bash acceptance/run_acceptance.sh

# ── Gherkin mutation (all features, parallel, workers 4) ──────────────────────
if [[ $SKIP_GHERKIN_MUTATION -eq 0 ]]; then
    if command -v gherkin-mutator &>/dev/null; then
        _run_gate "Gherkin mutation" bash acceptance/run_gherkin_mutation.sh
    else
        echo ""
        echo "━━━ Gherkin mutation ━━━"
        echo "  SKIP: gherkin-mutator not found"
        GATE_NAMES+=("Gherkin mutation")
        GATE_TIMES+=("skipped")
        GATE_STATUS+=("SKIP")
    fi
else
    GATE_NAMES+=("Gherkin mutation")
    GATE_TIMES+=("skipped")
    GATE_STATUS+=("SKIP")
fi

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║              Quality Gate Results             ║"
echo "╠══════════════════════════╦═════════╦══════════╣"
printf "║ %-24s ║ %-7s ║ %-8s ║\n" "Gate" "Status" "Time"
echo "╠══════════════════════════╬═════════╬══════════╣"
for i in "${!GATE_NAMES[@]}"; do
    name="${GATE_NAMES[$i]}"
    status="${GATE_STATUS[$i]}"
    elapsed="${GATE_TIMES[$i]}"
    printf "║ %-24s ║ %-7s ║ %-8s ║\n" "$name" "$status" "$elapsed"
done
echo "╚══════════════════════════╩═════════╩══════════╝"

# Exit 1 if any gate failed
for status in "${GATE_STATUS[@]}"; do
    [[ "$status" == "FAIL" ]] && exit 1
done
exit 0
