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
