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

# Pins for the external tools the gates need. `install-tools` is the only
# reader: ci.yml calls that recipe, so CI and a local run cannot disagree.
# drywall is a release of gabadi/drywall; gherkin-parser has no upstream tags,
# so its pin is a commit SHA.
DRYWALL_REPO := "gabadi/drywall"
DRYWALL_TAG := "v0.1.3"
GHERKIN_PARSER_REPO := "https://github.com/unclebob/Acceptance-Pipeline-Specification"
GHERKIN_PARSER_COMMIT := "accaa33d503340c56513ef387258f8da929ba902"

# Install the pinned drywall and gherkin-parser into ~/.local/bin. Rerunning is
# cheap: a tool already at its pin is left alone.
install-tools:
    #!/usr/bin/env bash
    set -euo pipefail
    BIN="$HOME/.local/bin"
    mkdir -p "$BIN"

    # drywall: one release asset per platform, stamped with its tag so a rerun
    # can tell it is current without downloading again.
    os="$(uname -s)"
    arch="$(uname -m)"
    case "$os-$arch" in
        Darwin-arm64)  asset=drywall-macos-aarch64 ;;
        Darwin-x86_64) asset=drywall-macos-x86_64 ;;
        Linux-x86_64)  asset=drywall-linux-x86_64 ;;
        *)
            echo "install-tools: no pinned drywall asset for $os/$arch" >&2
            exit 1
            ;;
    esac
    stamp="$BIN/.drywall.tag"
    if [ -x "$BIN/drywall" ] && [ "$(cat "$stamp" 2>/dev/null || true)" = "{{DRYWALL_TAG}}" ]; then
        echo "  ✓ drywall {{DRYWALL_TAG}} already in $BIN"
    else
        tmp="$(mktemp "$BIN/.drywall.XXXXXX")"
        url="https://github.com/{{DRYWALL_REPO}}/releases/download/{{DRYWALL_TAG}}/$asset"
        curl -fsSL -o "$tmp" "$url" || { rm -f "$tmp"; echo "install-tools: download failed: $url" >&2; exit 1; }
        chmod +x "$tmp"
        mv "$tmp" "$BIN/drywall"
        echo "{{DRYWALL_TAG}}" > "$stamp"
        echo "  ✓ drywall {{DRYWALL_TAG}} installed in $BIN"
    fi

    # gherkin-parser: built from source at the pinned commit. `go version -m`
    # reports the commit a binary was built from, which is the rerun check.
    if ! command -v go >/dev/null 2>&1; then
        echo "install-tools: go is needed to build gherkin-parser; install Go first" >&2
        exit 1
    fi
    target="$BIN/gherkin-parser"
    info="$(go version -m "$target" 2>/dev/null || true)"
    case "$info" in
        *"vcs.revision={{GHERKIN_PARSER_COMMIT}}"*)
            echo "  ✓ gherkin-parser {{GHERKIN_PARSER_COMMIT}} already in $BIN" ;;
        *)
            work="$(mktemp -d "${TMPDIR:-/tmp}/install-tools.XXXXXX")"
            trap 'rm -rf "$work"' EXIT
            git clone --quiet "{{GHERKIN_PARSER_REPO}}" "$work/src"
            git -C "$work/src" checkout --quiet "{{GHERKIN_PARSER_COMMIT}}"
            tmp="$(mktemp "$BIN/.gherkin-parser.XXXXXX")"
            (cd "$work/src" && go build -o "$tmp" ./cmd/gherkin-parser) || { rm -f "$tmp"; exit 1; }
            mv "$tmp" "$target"
            echo "  ✓ gherkin-parser {{GHERKIN_PARSER_COMMIT}} built into $BIN" ;;
    esac

    case ":$PATH:" in
        *":$BIN:"*) ;;
        *) echo "install-tools: warning: $BIN is not on PATH; add it to your shell profile" >&2 ;;
    esac

# --- The gate -------------------------------------------------------------

# Verbose gate output. Truncated at the start of every `just check`; gitignored.
LOG := "check.log"

# Test selection for `mutate`'s scored runs (#98): unit tests only. `integration`
# tests are coverage-blind and `component` tests are excluded too, so a Mutant
# that only a component test kills is scored a Survivor; the fix is a unit test
# that kills it (ADR 0023). `-p no:tach` skips tach's pytest plugin, which re-runs its
# impact analysis uncached on every subprocess spawn (~1-1.3s per Mutant, issue
# #26); `tach check` already covers it in the `lint` gate.
MUTATE_PYTEST_ARGS := "-p no:tach -m 'not integration and not component'"

# No argument runs everything CI runs, in CI's order. Naming gates runs
# exactly those, in the order given: `just check lint test`.
#
# Each gate's own stdout/stderr goes to LOG, not the terminal — only a ✓/✗ line
# per gate is printed, plus LOG's size and how to read it. This is the pattern
# issue 03 asked for: agents (the hardener loop in particular) driving this
# through a Bash tool pay for one line per gate, not one line per mutant —
# see `mutate` below, which applies the same shape to a single mutate4py run.
check *gates:
    #!/usr/bin/env bash
    set -euo pipefail
    all=(lint format-check test-unit test-component test-integration crap dry manifest acceptance)
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
    # `test-unit` writes both lcov.info and .coverage, and --no-deps means
    # nothing here will produce either on its own. `test-integration` is
    # coverage-blind, so it is never a prerequisite — see `test-unit`'s comment.
    # Each guard's `run:` must name the COMPLETE command.
    for needs_test in crap; do
        if [[ " ${selected[*]} " == *" ${needs_test} "* && " ${selected[*]} " != *" test-unit "* ]]; then
            echo "  ✗ ${needs_test} reads lcov.info, which \`test-unit\` writes" >&2
            echo "    run:  just check test-unit ${needs_test}" >&2
            exit 1
        fi
    done
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
    # A missing tool otherwise surfaces only when its gate runs, as exit 127,
    # after the gates before it have spent their minutes. Check them first.
    just --no-deps require-tools "${selected[@]}"
    : > "{{LOG}}"
    # An agent driving this through a Bash tool sees only the ✓/✗ lines, then
    # has to decide whether to read {{LOG}} — and a bare path says nothing
    # about whether that costs 200 tokens or 50k. Print the size AND the read
    # command that fits it, so the decision needs no exploratory `wc` round
    # trip. Sizes are the whole run's log, since `check` truncates it above.
    _log_hint() {
        local bytes lines tokens size how
        bytes=$(($(wc -c < "{{LOG}}")))
        lines=$(($(wc -l < "{{LOG}}")))
        tokens=$((bytes / 4))
        if ((bytes < 1024)); then size="${bytes} B"; else size="$((bytes / 1024)) KB"; fi
        if ((tokens >= 1000)); then tokens="~$((tokens / 1000))k tokens"; else tokens="~${tokens} tokens"; fi
        # Thresholds are budgets, not file facts, and the advice is a place to
        # START, never the whole read: tail lands on the last gate's output,
        # which is the failing one, but a gate that failed because an earlier
        # one left bad state needs the reader to keep going backwards. Erring
        # small — under ~6k chars whole-file is cheap enough not to bother
        # narrowing; past that, open a window first and widen it as needed.
        if ((bytes < 6000)); then
            how="fine to read whole"
        elif ((bytes < 40960)); then
            how="start with: tail -80 {{LOG}}"
        else
            how="start with: grep {{LOG}} — too big to read whole"
        fi
        echo "log: {{LOG}}, ${lines} lines, ${size}, ${tokens}; ${how}"
    }
    _run() {
        printf '\n=== %s ===\n' "$1" >> "{{LOG}}"
        if just --no-deps "$1" >> "{{LOG}}" 2>&1; then
            echo "  ✓ $1"
        else
            echo "  ✗ $1  ($(_log_hint))"
            exit 1
        fi
    }
    for gate in "${selected[@]}"; do
        _run "$gate"
    done
    echo "✓ check OK  ($(_log_hint))"

# Fails when a selected gate's external tool is missing. The tools are not
# Python dependencies, so nothing else would notice. `install-tools` puts them
# where this looks. drywall is resolved exactly as `dry` resolves it.
[private]
require-tools *gates:
    #!/usr/bin/env bash
    set -uo pipefail
    missing=0
    for gate in {{gates}}; do
        case "$gate" in
            dry)
                drywall="${DRYWALL:-$(command -v drywall 2>/dev/null || echo "$HOME/.local/bin/drywall")}"
                if ! command -v "$drywall" >/dev/null 2>&1; then
                    echo "  ✗ drywall not found; the dry gate needs it. Install it with: just install-tools" >&2
                    missing=1
                fi
                ;;
            acceptance)
                if ! command -v gherkin-parser >/dev/null 2>&1; then
                    echo "  ✗ gherkin-parser not found on PATH; the acceptance gate needs it. Install it with: just install-tools" >&2
                    missing=1
                fi
                ;;
        esac
    done
    exit "$missing"

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
# which test covers which line. Nothing in `check` reads those contexts since
# `context-deselection` and the test-context db went (#98), so the flag is a
# candidate for removal in a follow-up. `mutate` scores with unit tests only
# (MUTATE_PYTEST_ARGS), so moving a test to `component` costs it its place in
# the fast gate, the coverage metric and `mutate`'s scoring alike.
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
# Runs under pytest-xdist (`-n auto`): each test spawns its own interpreter and
# shares no state with the others, so they run in parallel (about 60 s serial,
# 31-42 s with `-n auto`, measured on #114). Under xdist pytest-cov combines the
# workers' data into .coverage on the controller. Checked on #114: after this
# gate appends, every unit and component context from the serial run is still
# there (only the self-scan test, deleted on #114, is gone) and lcov.info is
# unchanged.
[private]
test-integration:
    uv run pytest -m integration -n auto --cov --cov-append --cov-context=test \
        --cov-report= --cov-fail-under=0

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

# Fast CI-friendly mutation signal (one file, unit-test selection via `mutate`
# below). Not in `all` for the same reason it wasn't in CI before: real
# mutation scoring is slow. Opt in: `just check mutate-sample`.
[private]
mutate-sample:
    just mutate src/mutate4py/_cmd.py --allow-survivors

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
# Exit 3 (unaccepted survivors, ADR 0026) is a normal result: the report already lists them, so no tail.
#
# Rewrites `path`'s Manifest on a scored run: expect a diff. `--manifest-file`
# is always passed because src/ stores every Manifest as a sidecar; without it
# the run ignores the sidecar (scoring the whole file as Manifest-less) and
# embeds a second Manifest in the source (#110). A run that skips its
# Measurement prints no `Mutation Report`, so the filter also starts at its
# `Measurement: skipped` line, which keeps its recorded Survivors visible.
#
# MUTATE_PYTEST_ARGS (declared above the gates) selects unit tests only.
# `integration` tests are coverage-blind (see `test-integration`), and
# `component` tests are excluded too: a Mutant only a component test kills
# scores as a Survivor; the fix is a unit test that kills it (ADR 0023). `{{args}}` can
# override with an explicit --pytest-args, which changes this run's selection
# scope. `-p no:tach` skips tach's pytest plugin, which re-runs its impact
# analysis uncached on every subprocess spawn (~1-1.3s per mutant, issue #26);
# `tach check` already covers it in the `lint` gate.
mutate path *args:
    #!/usr/bin/env bash
    set -uo pipefail
    log="$(mktemp)"
    trap 'rm -f "$log"' EXIT
    uv run mutate4py {{path}} --pytest-args "{{MUTATE_PYTEST_ARGS}}" {{args}} --manifest-file >"$log" 2>&1
    status=$?
    awk '/^Mutation Report$/ || /^Measurement: skipped/ {shown=1} shown' "$log"
    if [ "$status" -ne 0 ] && [ "$status" -ne 3 ]; then
        echo ""
        echo "--- mutate4py exited $status; last 20 lines of $log ---"
        tail -20 "$log"
    fi
    exit "$status"

# --- Perf benchmark ----------------------------------------------------------
#
# Times every quality check `check` runs, plus a real mutation run over src/
# (the default scored run: per-mutant test selection, differential once the
# Manifests exist, so it re-scores only what changed), and prints a duration
# table with a total.
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
    _run "mutation (src/)" \
        just mutate src/ --mutation-warning 100000 --allow-survivors

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
