# ADR 0002 — `--scan` prints counts only; no manifest logic in F1

- Status: accepted
- Date: 2026-06-25
- Feature: F1 (`site-discovery`)
- Spec: docs/spec.md §8 (`--scan` output), §5 (manifest — F2)

## Context

F1 makes site discovery observable end-to-end through a thin CLI. The user-facing
affordance is `mutate4py <file> --scan`, reproducing mutate4go's `--scan`: a block
of *counts*, no tests run, nothing written to the file.

The module-mirror sibling `mutate4js` bundled manifest *reading/diffing* into the
same deliverable as `--scan` (its ADR 0002), so its `--scan` computes `Changed` by
diffing discovered units against an embedded manifest. **mutate4py splits
differently**: per `docs/plan.md`, all manifest logic — read, diff, and write —
lives in **F2**, not F1. F1 ships zero manifest code.

## Decision

`mutate4py <file> --scan` prints exactly the §8 scan block and nothing more:

```
Mutation scan: <file>
Total mutation sites: <n>
Changed mutation sites: <n>
Manifest exists: <true|false>
```

…plus `Warning: <n> mutation sites exceeds threshold <m>.` when `n` exceeds the
warning threshold (default 50).

**In F1, with no manifest code present:**

- `Manifest exists:` is always **`false`**.
- `Changed mutation sites:` always equals `Total mutation sites:` (no prior
  baseline ⇒ every site is changed) — this is mutate4go's no-manifest behavior.

**`--scan` is strictly read-only and quiet:** no coverage acquired, no test command
run, no file write, no per-site listing. Per-operator and per-attribution
correctness is a unit-test concern (ADR 0001), not a CLI affordance — adding a
site-listing flag would be a fabrication beyond mutate4go's surface (mutate4js ADR
0001).

## Consequences

- F1's `_qa.feature` asserts the four count lines, the warning line over threshold,
  the always-`false` manifest line, and `Changed == Total` — all observable through
  the CLI with no manifest fixture needed.
- **F2 reopens this:** once the manifest reader/differ lands, `--scan` gains the
  `Manifest exists: true` / `Changed < Total` path. F2 must add a fixture with a
  hand-placed manifest footer and a scenario exercising the diff. This ADR's
  "always false / changed == total" claims are scoped to F1 and expected to be
  superseded for the manifest-present path.

## Alternatives considered

- **Bundle the manifest differ into F1 (mutate4js's split)** — rejected: our plan
  keeps the manifest a single coherent feature (F2: read + diff + write together),
  avoiding a half-built manifest module spanning two features.
- **A `--scan` per-site listing** — rejected: a seventh fabrication beyond
  mutate4go's surface (mutate4js ADR 0001, spec §10).
