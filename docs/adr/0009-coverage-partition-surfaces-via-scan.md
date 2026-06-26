# F3's covered/uncovered partition surfaces through `--scan`

**Status:** accepted
**Feature:** F3 (coverage-gate) · **Spec:** §6, §8

## Decision

The coverage gate (F3) has no CLI *mode* of its own: coverage is a gate that sits
between site discovery (F1) and the run loop (F4), not a verb a user invokes. To keep
every feature independently end-to-end testable (the plan's per-feature `_qa.feature`
rule), F3 makes its `covered` / `uncovered` partition observable by **extending the
`--scan` output**. When a coverage source is supplied alongside `--scan`, the §8 scan
block gains two lines:

```
Mutation scan: <file>
Total mutation sites: <n>
Covered mutation sites: <c>
Uncovered mutation sites: <u>
Manifest exists: <true|false>
```

`Covered + Uncovered == Total`. When **no** coverage source is supplied, `--scan` prints
its F1 block unchanged (no Covered/Uncovered lines) — coverage lines appear only when
coverage was acquired.

## Why `--scan` and not a new flag or the run report

- **Not a new diagnostic flag.** A dedicated `--coverage-report` flag would be surface
  debt: F5's mutual-exclusion matrix would have to absorb a flag that exists only to
  make F3 testable.
- **Not the run report.** mutate4js (the mirror) prints `Covered/Uncovered` in its run
  header, but mutate4py's plan deliberately keeps the **full run report in F4**
  (`run-loop`). Putting the partition in F4's report would make F3 un-testable on its
  own. So mutate4py diverges from the mirror's placement: the partition surfaces in
  `--scan`, the run-report's uncovered block stays F4.
- **Consistent with F1→F5.** F1 wrote `Manifest exists` / `Changed` into `--scan` and
  deferred their full *wiring* to F5; F3 does the same for `Covered/Uncovered`.

## Feature boundary

- **F3 (here):** the two new `--scan` lines and the gate that computes them when a
  coverage source is given.
- **F5 (cli-surface):** the full `--scan` flag-combination validation — including
  whether `--scan` + a coverage flag is permitted, and the coverage flags'
  pairwise-exclusivity wiring (ADR 0008). F3 specifies the *output*; F5 owns the parse
  matrix around it.
- **F4 (run-loop):** the full-run report's uncovered block — distinct from `--scan`.
