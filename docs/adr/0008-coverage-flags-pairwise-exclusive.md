# The three coverage-acquisition flags are pairwise-exclusive, not a precedence order

**Status:** superseded (2026-11-13) by ADR 0027

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

## Superseded (2026-11-13)

The three flags no longer exist, so there is nothing left to be exclusive. `--cov-cmd`,
`--lcov` and `--reuse-coverage` were removed in 0.3.0: a scored run measures coverage
itself (ADR 0027), and passing any of them exits 2 with "removed in 0.3.0: the run
measures coverage itself". The refusal names the first removed flag it finds; it does
not try to rank them. The fail-loud posture above still holds: a removed flag is
rejected, never ignored.
