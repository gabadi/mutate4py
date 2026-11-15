# Line coverage only — `BRDA` branch data is deliberately discarded

**Status:** accepted; the default path is superseded (2026-11-13) by ADR 0027. The line-only gate stays.

A site is eligible iff its line has an LCOV `DA:<line>,<count>` with `count > 0`.
Branch records (`BRDA`) are parsed and **thrown away**.

This looks like an oversight and is not. Gating on branch coverage would suppress
exactly the boundary survivors the tool exists to find: `>` → `>=` on a line whose
branches are only partially covered is the highest-value mutant in the file, and
branch-gating would never select it. Matches mutate4go.

`--reuse-coverage` reads **`coverage.lcov`**, not `lcov.info`. A missing file is a
hard error, never a silent skip.

## Superseded: the default path (2026-11-13)

The covered lines now come from the Measurement (ADR 0027), not from `coverage.lcov`.
A line is eligible iff any test context reached it, Empty context included. That is
the line-only rule above, applied to the Measurement's data. Branch data is still
discarded, and the line-only gate stays. `--cov-cmd`, `--lcov` and `--reuse-coverage`
were removed in 0.3.0 (ADR 0008), so no run reads `coverage.lcov` or any LCOV file.
