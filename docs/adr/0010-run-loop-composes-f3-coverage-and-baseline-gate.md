# The run loop acquires coverage through F3's flags and gates on a passing baseline

**Status:** accepted
**Feature:** F4 (run-loop) · **Spec:** §6, §7

Two run-loop decisions where `mutate4py` deliberately diverges from `mutate4go`'s
`internal/runner/runner.go`, both forced by the Python coverage substrate and both
expensive to change once the run report is a published contract.

## Coverage acquisition reuses F3's three flags, not a `-coverprofile` append

`mutate4go`'s `Mutate` calls `ensureCoverage`, which appends `-coverprofile=<path>`
to the test command and reads Go's `target/coverage/coverage.out`. Python has no
universal coverage flag (spec §1, §6 [PY]), so the run loop **composes F3's already-
shipped acquisition** instead: exactly one of `--cov-cmd <CMD>` (run once), `--lcov
<PATH>`, or `--reuse-coverage` (default `coverage.lcov`). F4 does not re-implement
acquisition or the line gate — it calls F3 and partitions the discovered sites with
F3's covered/uncovered result.

**`--reuse-coverage` prints the stale-coverage warning.** Upstream prints
`Reusing existing coverage; covered/uncovered classification may be stale.`
(`runner.go:274`) on the reuse path. F3 never emitted this — it surfaced only in the
`--scan` partition, not a run. F4 owns the line and prints it verbatim on the
`--reuse-coverage` run path, before the header. A future reader should know this line
is the run loop's, not F3's `--scan` surface.

## The baseline must pass, and its failure aborts with `baseline failed:`

Before any mutant is applied, the run loop executes `--test-command` (default
`pytest`, spec §2 [PY]) **once on the unmutated source**. Two outcomes:

- **Pass** → its wall-clock duration sets `timeout = max(1s, timeout-factor ×
  baseline)`. The `max(1s, …)` floor is a port of upstream (`runner.go:228`); a
  sub-second baseline must not produce a sub-second mutant timeout that flaps.
- **Fail** → the run **aborts before the per-site loop**, exits non-zero, and prints
  `baseline failed: <reason>` (ports upstream `fmt.Errorf("baseline failed: %w", err)`,
  `runner.go:225`). No mutant is applied, no `.mutate4py.bak` is written, no report is
  printed. A failing test suite on clean source would make every mutant trivially
  "survive" (or every run meaningless), so the baseline is a hard gate, not a warning.

The baseline runs **after** coverage acquisition and partition, and **before** the
backup is saved — the order is observable (a baseline failure leaves no backup).
