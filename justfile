# Local commands. `just check` mirrors CI (.github/workflows/ci.yml) exactly —
# same commands, same order — so a green local run means a green pipeline.
# Every gate command lives in exactly one recipe here; CI and `perf` call the
# recipes rather than restating them, so no copy can silently drift.

# Default: list recipes.
default:
    @just --list

# --- Setup --------------------------------------------------------------

install:
    uv sync

# --- The gate -------------------------------------------------------------

# Verbose gate output. Truncated at the start of every `just check`; gitignored.
LOG := "check.log"

# Single source of truth for which tests exist for this project's scored
# `mutate` runs. Both `test-context-db` (builds the db `mutate` narrows
# against) and `mutate` itself (the scored run's own --pytest-args) read this
# ONE variable, so the db's contexts and the Mutant run's own test selection
# can't silently drift apart into two argument sets that disagree.
MUTATE_PYTEST_ARGS := "-p no:tach -m 'not integration'"

# Isolated-session test-context db `mutate` reads via --test-contexts (see
# `test-context-db` below). Its cache sidecar is
# TEST_CONTEXT_DB + ".test-context-cache.json" (mutate4py's own convention);
# both are gitignored.
TEST_CONTEXT_DB := "contexts.db"

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
    all=(lint format-check test-unit test-component test-integration context-deselection crap dry manifest acceptance)
    extra=(gherkin-mutation mutate-sample test-context-db)
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
    # `test-unit` writes both lcov.info and .coverage, and --no-deps means
    # nothing here will produce either on its own. `test-integration` is
    # coverage-blind, so it is never a prerequisite — see `test-unit`'s comment.
    # Each guard's `run:` must name the COMPLETE command: mutate-sample also
    # needs test-context-db (next guard) and context-deselection also needs
    # test-component (guard after that), and fixing one must not trip another.
    for needs_test in crap mutate-sample context-deselection; do
        if [[ " ${selected[*]} " == *" ${needs_test} "* && " ${selected[*]} " != *" test-unit "* ]]; then
            echo "  ✗ ${needs_test} reads lcov.info/.coverage, which \`test-unit\` writes" >&2
            case "${needs_test}" in
                mutate-sample)       echo "    run:  just check test-unit test-context-db mutate-sample" >&2 ;;
                context-deselection) echo "    run:  just check test-unit test-component context-deselection" >&2 ;;
                *)                   echo "    run:  just check test-unit ${needs_test}" >&2 ;;
            esac
            exit 1
        fi
    done
    # `crap` and `mutate-sample` read lcov.info, which is unit-only by design.
    # `context-deselection` reads .coverage instead, and needs EVERY context a
    # Mutant run could narrow against — `component` tests are narrowing
    # candidates (MUTATE_PYTEST_ARGS excludes only `integration`), so their
    # append has to have happened before this gate reads the file.
    if [[ " ${selected[*]} " == *" context-deselection "* && " ${selected[*]} " != *" test-component "* ]]; then
        echo "  ✗ context-deselection must see every narrowable context; \`test-component\` appends the rest" >&2
        echo "    run:  just check test-unit test-component context-deselection" >&2
        exit 1
    fi
    # `mutate` (which `mutate-sample` shells out to) depends on `test-context-db`
    # itself, so it always builds/refreshes the db it needs — this guard isn't
    # for correctness. It's for cost: that dependency can be a ~16-minute cold
    # build (see `test-context-db`'s own comment for the measured figure), and
    # without this guard it would run silently, nested inside `mutate-sample`,
    # with no gate of its own in {{LOG}} and no ✓/✗ line. Selecting
    # `test-context-db` explicitly makes that cost visible up front instead.
    if [[ " ${selected[*]} " == *" mutate-sample "* && " ${selected[*]} " != *" test-context-db "* ]]; then
        echo "  ✗ mutate-sample builds the test-context db via \`mutate\`'s own dependency; make that cost visible as its own gate" >&2
        echo "    run:  just check test-unit test-component test-context-db mutate-sample" >&2
        exit 1
    fi
    # The append chain runs test-unit -> test-component -> test-integration.
    # Only test-unit starts the data file; either later gate on its own would
    # append to whatever stale data happened to be on disk.
    if [[ " ${selected[*]} " == *" test-component "* && " ${selected[*]} " != *" test-unit "* ]]; then
        echo "  ✗ test-component appends to test-unit's coverage; run both" >&2
        echo "    run:  just check test-unit test-component" >&2
        exit 1
    fi
    if [[ " ${selected[*]} " == *" test-integration "* && ( " ${selected[*]} " != *" test-unit "* || " ${selected[*]} " != *" test-component "* ) ]]; then
        echo "  ✗ test-integration appends to test-unit's and test-component's coverage; run all three" >&2
        echo "    run:  just check test-unit test-component test-integration" >&2
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

# Three gates so a slow or flaky test shows up as itself rather than as
# "tests took a while": `integration` tests each spawn a fresh interpreter
# (9% of the suite, about half its wall clock); `component` tests are the
# slowest of the remainder (real subprocess/fork execution via an Executor,
# but in-process); `test-unit` runs the fast remainder (issue #71).
#
# Coverage is measured on `test-unit` ALONE: it writes the data, emits
# lcov.info, and applies the threshold. The other two append to .coverage
# afterwards without touching lcov.info or any threshold, so both the coverage
# gate and the CRAP score `crap` computes from lcov.info are unit-only.
# Deliberate: `component` runs real subprocess/fork execution through
# mutate4py's own Executor — integration-nature work that merely happens to
# stay in-process and therefore coverage-visible, and visibility is an
# implementation accident, not a reason to count it in a unit metric.
# `test-integration` is coverage-blind outright (see its own comment).
# Reasoning and evidence: docs/adr/0023-unit-component-integration-test-split.md.
#
# .coverage still accumulates all three, because --cov-context=test records
# which test covers which line and `context-deselection` below needs EVERY
# narrowable context, not just the unit ones. `mutate` narrows against
# `contexts.db` instead (ADR 0021), and MUTATE_PYTEST_ARGS excludes only
# `integration` — so moving a test to `component` costs it its place in the
# fast gate and in the coverage metric, not its place in narrowing.
[private]
test-unit:
    uv run pytest -m 'not integration and not component' --cov --cov-context=test \
        --cov-report=lcov:lcov.info --cov-report=term-missing --cov-fail-under=90

# Appends its contexts to test-unit's data. Emits no report and applies no
# threshold: the measurement already closed (see above).
[private]
test-component:
    uv run pytest -m component --cov --cov-append --cov-context=test \
        --cov-report= --cov-fail-under=0

# Coverage-blind: COVERAGE_PROCESS_START is unset, so a spawned interpreter's
# execution is invisible to the parent's .coverage. Measured — lcov.info and
# the named-context set are identical with and without this gate (ADR 0023).
# It still appends so that enabling subprocess coverage later lands the data
# in the same file instead of needing this plumbing rebuilt.
[private]
test-integration:
    uv run pytest -m integration --cov --cov-append --cov-context=test \
        --cov-report= --cov-fail-under=0

# No test recorded as a named context in `.coverage` may be deselected by the
# `mutate` recipe's --pytest-args below: narrowing could still pick that
# test's node ID for some Site, the marker filter then deselects it, and
# pytest exits 5/4 -- which _cmd.py's classify_exit_code (#55) now raises on
# instead of scoring `killed`, aborting the whole mutation run mid-batch over
# a misconfiguration this gate catches ahead of time instead. Requires
# .coverage from `test-unit` + `test-component` (see `check`'s guards).
[private]
context-deselection:
    uv run python scripts/check_context_deselection.py

# Requires lcov.info from `test-unit`.
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
# skips it; run explicitly: `just check gherkin-mutation`.
gherkin-mutation:
    bash acceptance/run_gherkin_mutation.sh

# Fast CI-friendly mutation signal (one file, full test suite via `mutate`
# below). Not in `all` for the same reason it wasn't in CI before: real
# mutation scoring is slow. Opt in: `just check test-unit test-context-db
# mutate-sample` (see the `check` guard above for why test-context-db is
# listed explicitly rather than left implicit).
[private]
mutate-sample:
    just mutate src/mutate4py/_cmd.py --mutate-all

# Builds (or, on a fresh cache, skips rebuilding — mutate4py's own staleness
# cache, see docs/adr/0022 and issue #52) the isolated-session test-context
# db `mutate` below reads via --test-contexts (ADR 0021), scoped by the SAME
# MUTATE_PYTEST_ARGS `mutate` itself uses for scoring — one declared argument
# set for both, instead of restating the string in two places that could
# silently disagree.
#
# `mutate` also declares this as its own dependency, so a bare `just mutate
# <path>` always builds or refreshes it first — a stale db is never narrowed
# against silently, it's rebuilt (the cache's own staleness check, ADR 0022).
# Cost: ~16 minutes cold on this project's full non-integration suite (957
# tests, measured; ADR 0021 accepts this class of cost as deliberate), ~4s on
# an unchanged tree.
#
# Decision: not in `all`, and .github/workflows/ci.yml is deliberately left
# unchanged — CI does not invoke mutate or mutate-sample at all, and this
# recipe doesn't change that. A fresh CI checkout has no
# warm cache, so folding this into the default `just check` would add ~16 cold
# minutes to every run; local/hardener use (which does warm the cache) is
# unaffected. Revisit only as its own deliberate change, not a side effect of
# this recipe existing.
[private]
test-context-db:
    uv run mutate4py --build-test-contexts {{TEST_CONTEXT_DB}} --pytest-args "{{MUTATE_PYTEST_ARGS}}"

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
# Requires lcov.info from `just check test-unit` first — REWRITES `path`
# afterward, same as mutate4py always does on a scored run: expect a diff.
#
# --test-contexts reads {{TEST_CONTEXT_DB}}, not `.coverage`: a single shared
# --cov-context=test session under-lists covering tests for any line more than
# one test reaches (ADR 0021), so narrowing against it can silently score a
# Mutant `survived` when a killing test exists but was never selected. The
# `test-context-db` dependency above builds or refreshes the sound
# isolated-session replacement on every run, so this never narrows against a
# missing or stale db.
#
# MUTATE_PYTEST_ARGS excludes `integration` because those tests are
# coverage-blind (see `test-integration`) and so never contribute to
# per-mutant scoping — confirmed 0/346 sites depend on them; they only cost
# baseline and full-suite-fallback time. `{{args}}` can override with an
# explicit --pytest-args, which changes this run's selection scope but not
# what `test-context-db` already built the db from — see that recipe on why
# both read one variable. `-p no:tach` skips tach's pytest plugin, which
# re-runs its impact analysis uncached on every subprocess spawn (~1-1.3s per
# mutant, issue #26); `tach check` already covers it in the `lint` gate.
mutate path *args: test-context-db
    #!/usr/bin/env bash
    set -uo pipefail
    log="$(mktemp)"
    trap 'rm -f "$log"' EXIT
    uv run mutate4py {{path}} --lcov lcov.info --test-contexts {{TEST_CONTEXT_DB}} --pytest-args "{{MUTATE_PYTEST_ARGS}}" {{args}} >"$log" 2>&1
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
# Every step below calls the gate recipe rather than restating its command,
# so timings measure what `check` and CI actually run. Restated copies drift:
# these three test steps once carried their own --cov flags and kept the old
# arrangement (integration emitting lcov.info) after the recipes moved on.
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
    _run "test (unit)"        just --no-deps test-unit
    _run "test (component)"   just --no-deps test-component
    _run "test (integration)" just --no-deps test-integration
    _run "crap"   uv run crap4py src/ --lcov lcov.info --max-crap 6
    DRYWALL="${DRYWALL:-$(command -v drywall 2>/dev/null || echo "$HOME/.local/bin/drywall")}"
    _run "dry"    "$DRYWALL" src/
    _run "check-manifest" uv run mutate4py src/ --check-manifest --manifest-file
    _run "acceptance" bash acceptance/run_acceptance.sh
    _run "test-context-db" just --no-deps test-context-db
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
