# The three coverage-acquisition flags are pairwise-exclusive, not a precedence order

**Status:** accepted

`--cov-cmd`, `--lcov`, and `--reuse-coverage` each acquire LCOV a different way.
Supplying more than one is a **usage error**, not a precedence order that silently
ignores the losers.

mutate4go gives no precedent here — it has exactly one coverage path (it appends
`-coverprofile=` to the test command), so this is Python-only territory. The choice
follows the rest of the CLI's fail-loud posture: every other flag conflict in the
tool is rejected rather than resolved.

**Rejected:** a precedence order (e.g. `--lcov` > `--reuse-coverage` > `--cov-cmd`)
— silently discarding a flag the user deliberately passed is the "wrong results
without telling you" failure the tool's hard errors exist to prevent.
