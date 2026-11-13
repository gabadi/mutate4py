# Line coverage only — `BRDA` branch data is deliberately discarded

**Status:** accepted

A site is eligible iff its line has an LCOV `DA:<line>,<count>` with `count > 0`.
Branch records (`BRDA`) are parsed and **thrown away**.

This looks like an oversight and is not. Gating on branch coverage would suppress
exactly the boundary survivors the tool exists to find: `>` → `>=` on a line whose
branches are only partially covered is the highest-value mutant in the file, and
branch-gating would never select it. Matches mutate4go.

`--reuse-coverage` reads **`coverage.lcov`**, not `lcov.info`. A missing file is a
hard error, never a silent skip.

## Superseded: the no-flag default path (2026-11-13)

On a run given none of `--cov-cmd`, `--lcov` or `--reuse-coverage`, the covered
lines now come from the Measurement (ADR 0027), not from `coverage.lcov`. A line
is eligible iff any test context reached it, Empty context included. That is the
line-only rule above, applied to the Measurement's data. Branch data is still
discarded. The `coverage.lcov` rules above still hold for runs given a coverage
flag.
