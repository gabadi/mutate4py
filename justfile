# Local commands. `just check` mirrors CI (.github/workflows/ci.yml) exactly —
# same commands, same order — so a green local run means a green pipeline.
# Replaces check.sh and perf.sh: one source of truth for gate commands instead
# of three copies (CI yaml, check.sh, perf.sh) that could silently drift.

# Default: list recipes.
default:
    @just --list

# --- Setup --------------------------------------------------------------

install:
    uv sync

# --- The gate -------------------------------------------------------------

# Verbose gate output. Truncated at the start of every `just check`; gitignored.
LOG := "check.log"

# No argument runs everything CI runs, in CI's order. Naming gates runs
# exactly those, in the order given: `just check lint test`.
#
# Each gate's own stdout/stderr goes to LOG, not the terminal — only a ✓/✗ line
# per gate is printed, with the log tailed on failure. This is the pattern
# issue 03 asked for: agents (the hardener loop in particular) driving this
# through a Bash tool pay for one line per gate, not one line per mutant —
# see `mutate` below, which applies the same shape to a single mutate4py run.
check *gates:
    #!/usr/bin/env bash
    set -euo pipefail
    all=(lint format-check test-unit test-integration crap dry manifest acceptance)
    extra=(gherkin-mutation mutate-sample)
    known=("${all[@]}" "${extra[@]}")
    selected=({{gates}})
    if [ ${#selected[@]} -eq 0 ]; then
        selected=("${all[@]}")
    fi
    # The gates are [private], so `just --list` cannot show the names. Say them
    # here rather than letting a typo read as a gate that failed.
    for gate in "${selected[@]}"; do
        if [[ " ${known[*]} " != *" ${gate} "* ]]; then
            echo "  ✗ no such gate: ${gate}" >&2
            echo "    gates: ${known[*]}" >&2
            exit 1
        fi
    done
    # `crap` and `mutate-sample` read artifacts (lcov.info / .coverage) that
    # only `test-integration` writes, and --no-deps means nothing here will
    # produce them. It writes them for BOTH halves — see its own comment.
    for needs_test in crap mutate-sample; do
        if [[ " ${selected[*]} " == *" ${needs_test} "* && " ${selected[*]} " != *" test-integration "* ]]; then
            echo "  ✗ ${needs_test} reads lcov.info/.coverage, which only \`test-integration\` writes" >&2
            echo "    run:  just check test-unit test-integration ${needs_test}" >&2
            exit 1
        fi
    done
    # test-integration appends to test-unit's coverage data. Running it alone
    # would measure 80 tests and fail --cov-fail-under, which reads as a
    # coverage regression rather than the missing half it is.
    if [[ " ${selected[*]} " == *" test-integration "* && " ${selected[*]} " != *" test-unit "* ]]; then
        echo "  ✗ test-integration appends to test-unit's coverage; run both" >&2
        echo "    run:  just check test-unit test-integration" >&2
        exit 1
    fi
    : > "{{LOG}}"
    _run() {
        printf '\n=== %s ===\n' "$1" >> "{{LOG}}"
        if just --no-deps "$1" >> "{{LOG}}" 2>&1; then
            echo "  ✓ $1"
        else
            echo "  ✗ $1  (log: {{LOG}})"
            exit 1
        fi
    }
    for gate in "${selected[@]}"; do
        _run "$gate"
    done
    echo "✓ check OK  (log: {{LOG}})"

[private]
lint:
    uv run ruff check src/ tests/
    uv run tach check

[private]
format-check:
    uv run ruff format --check src/ tests/

# Rewrite files rather than just reporting.
format:
    uv run ruff format src/ tests/

# The suite runs in two halves so a slow or flaky integration test is visible
# as itself rather than as "tests took a while": 80 integration tests are 9% of
# the suite and about half its wall clock, because each one spawns a fresh
# interpreter.
#
# They are two halves of ONE coverage measurement, not two measurements.
# test-unit writes the data; test-integration appends to it and only then
# writes lcov.info and applies the threshold. Splitting the data instead would
# turn the `crap` gate red: those 80 tests cover 2 statements nothing else
# reaches, and without them `_wait_for_child` scores 6.2 against a cap of 6.
# The two halves must therefore stay in the same job, on the same machine,
# in this order.
#
# --cov-context=test records which test covers which line in .coverage
# (sqlite), which `mutate`'s --test-contexts reads for per-mutant test
# selection.
[private]
test-unit:
    uv run pytest -m 'not integration' --cov --cov-context=test \
        --cov-report= --cov-fail-under=0

# Appends to test-unit's coverage data, then reports on the total. The
# threshold and lcov.info always describe the whole suite.
[private]
test-integration:
    uv run pytest -m integration --cov --cov-append --cov-context=test \
        --cov-report=lcov:lcov.info --cov-report=term-missing --cov-fail-under=90

# Requires lcov.info from `test`.
[private]
crap:
    uv run crap4py src/ --lcov lcov.info --max-crap 6

[private]
dry:
    #!/usr/bin/env bash
    set -euo pipefail
    DRYWALL="${DRYWALL:-$(command -v drywall 2>/dev/null || echo "$HOME/.local/bin/drywall")}"
    "$DRYWALL" src/

[private]
manifest:
    uv run mutate4py src/ --check-manifest --manifest-file

[private]
acceptance:
    bash acceptance/run_acceptance.sh

# Needs gherkin-mutator installed locally (CI doesn't run this — only
# gherkin-parser is installed there). Not in `all`, so `just check` alone
# skips it; run explicitly: `just check test gherkin-mutation`.
gherkin-mutation:
    bash acceptance/run_gherkin_mutation.sh

# Fast CI-friendly mutation signal (one file, full test suite via `mutate`
# below). Not in `all` for the same reason it wasn't in CI before: real
# mutation scoring is slow. Opt in: `just check test mutate-sample`.
[private]
mutate-sample:
    just mutate src/mutate4py/_cmd.py --mutate-all

# --- Mutation testing (hardener loop) ---------------------------------------
#
# Scored, potentially slow mutate4py run. `_runner.py` prints one
# `[i/total] <status> line N ...` line per mutation site unconditionally
# (`hardender.prompt` used to mandate this be run in verbose mode on top of
# that) — captured in full by an agent's Bash tool on every hardening
# iteration. This captures that stream to a log instead and prints only the
# `Mutation Report` block (Killed/Survived/Uncovered counts + every
# Survivor's line/desc, still fully actionable) — ~5,100 → ~450 tokens per
# full-src/ pass (issue 03). Full log kept on failure/error (tail -20) so an
# infra failure that happens before the summary prints is still visible.
#
# Requires `.coverage`/lcov.info from `just test` (or `just check test`)
# first — REWRITES `path` afterward, same as mutate4py always does on a
# scored run: expect a diff.
#
# Default --pytest-args excludes @pytest.mark.integration tests (the
# subprocess-spawning `_run_cli_path`/`_run_cli_in` CLI tests in
# tests/test_main.py): pytest-cov's --cov-context=test can't see inside a
# spawned subprocess, so these tests never contribute to per-mutant test
# scoping (confirmed: 0/346 sites depend on them) — they only added cost to
# the once-per-run baseline and any full-suite fallback. `{{args}}` can still
# override with an explicit --pytest-args if ever needed.
# `-p no:tach` skips tach's pytest plugin, which re-runs its impact analysis
# on every subprocess spawn with no cache (measured ~1-1.3s/mutant, issue
# #26 diagnosis) — irrelevant here since `tach check` already runs in the
# `lint` gate; this only drops its redundant per-mutant pytest-plugin cost.
mutate path *args:
    #!/usr/bin/env bash
    set -uo pipefail
    log="$(mktemp)"
    trap 'rm -f "$log"' EXIT
    uv run mutate4py {{path}} --lcov lcov.info --test-contexts .coverage --pytest-args "-p no:tach -m 'not integration'" {{args}} >"$log" 2>&1
    status=$?
    awk '/^Mutation Report$/,0' "$log"
    if [ "$status" -ne 0 ]; then
        echo ""
        echo "--- mutate4py exited $status; last 20 lines of $log ---"
        tail -20 "$log"
    fi
    exit "$status"

# --- Perf benchmark ----------------------------------------------------------
#
# Times every quality check `check` runs, plus a real, full-src/ mutation run
# using per-mutant test selection, and prints a duration table with a total.
# Not a pre-commit gate — dogfoods mutate4py against all of src/, so this
# takes minutes, not seconds. Run it to benchmark real mutation-testing cost.
#
# The mutation step below calls `mutate` above rather than invoking
# mutate4py directly, so this — the largest run in the project — always
# gets the same `-p no:tach` plugin-disable and integration-test exclusion
# as every other scored run, with one invocation to keep in sync instead of
# two that can silently drift apart.
perf:
    #!/usr/bin/env bash
    set -uo pipefail
    log="$(mktemp)"
    trap 'rm -f "$log"' EXIT
    declare -a names durations statuses
    _run() {
        local name="$1"; shift
        local start=$SECONDS status="ok"
        if ! "$@" >"$log" 2>&1; then status="FAILED"; fi
        local elapsed=$((SECONDS - start))
        names+=("$name"); durations+=("${elapsed}s"); statuses+=("$status")
        if [[ "$status" == "FAILED" ]]; then
            echo ""
            echo "--- failure output: $name ---"
            tail -20 "$log"
        fi
    }
    _run "lint"   uv run ruff check src/ tests/
    _run "tach"   uv run tach check
    _run "format" uv run ruff format --check src/ tests/
    _run "test (unit)" uv run pytest -m 'not integration' --cov \
                      --cov-context=test --cov-report= --cov-fail-under=0 -q
    _run "test (integration)" uv run pytest -m integration --cov --cov-append \
                      --cov-context=test --cov-report=lcov:lcov.info \
                      --cov-report=term-missing --cov-fail-under=90 -q
    _run "crap"   uv run crap4py src/ --lcov lcov.info --max-crap 6
    DRYWALL="${DRYWALL:-$(command -v drywall 2>/dev/null || echo "$HOME/.local/bin/drywall")}"
    _run "dry"    "$DRYWALL" src/
    _run "check-manifest" uv run mutate4py src/ --check-manifest --manifest-file
    _run "acceptance" bash acceptance/run_acceptance.sh
    _run "mutation (src/, --test-contexts)" \
        just mutate src/ --mutate-all --mutation-warning 100000

    name_width=0
    for n in "${names[@]}"; do
        (( ${#n} > name_width )) && name_width=${#n}
    done
    echo ""
    printf "%-${name_width}s  %8s   %s\n" "check" "duration" "status"
    printf '%.0s-' $(seq 1 $((name_width + 22))); echo ""
    total=0
    for i in "${!names[@]}"; do
        printf "%-${name_width}s  %8s   %s\n" "${names[$i]}" "${durations[$i]}" "${statuses[$i]}"
        total=$((total + ${durations[$i]%s}))
    done
    printf '%.0s-' $(seq 1 $((name_width + 22))); echo ""
    printf "%-${name_width}s  %7ss\n" "total" "$total"
    for status in "${statuses[@]}"; do
        [[ "$status" == "FAILED" ]] && exit 1
    done
    exit 0
