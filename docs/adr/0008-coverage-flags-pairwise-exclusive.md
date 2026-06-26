# The three coverage-acquisition flags are pairwise-exclusive

**Status:** accepted
**Feature:** F3 (coverage-gate) · **Spec:** §6, §2

mutate4py acquires LCOV coverage three ways — `--cov-cmd CMD` (run once, must emit
LCOV), `--lcov PATH` (a pre-generated file), and `--reuse-coverage` (read the default
on-disk path `coverage.lcov`, see ADR 0007). **Supplying more than one of these in a
single invocation is a usage error** (exit non-zero), rather than a precedence order
that silently ignores the lower-priority flags.

## Why exclusive over precedence

`mutate4go`'s posture is strict, fail-loud mutual exclusion: `--scan` /
`--update-manifest`, and `--since-last-run` / `--mutate-all` / `--lines` are all
rejected when combined. A precedence order would silently discard a flag the user
deliberately passed — exactly the "wrong results without telling you" failure the
tool's hard errors exist to prevent. Pairwise exclusivity keeps coverage acquisition
consistent with the rest of the CLI and makes the source of truth for coverage
unambiguous. Matches `mutate4js` ADR 0004.

**Not a simple port.** `mutate4go` has exactly one coverage path (it appends
`-coverprofile=...` to the test command), so upstream gives no precedent for how three
coverage flags should combine; this is `[PY]` territory the spec left open.

## Feature boundary — behaviour here, validation wiring in F5

F3 owns the **behaviour**: each of the three modes acquires coverage and feeds the
partition, and a missing/empty source for a chosen mode is a hard error. The full
**mutual-exclusion validation matrix** — coverage flags being pairwise-exclusive *and*
incompatible with `--scan`/execution options — is wired in **F5 (cli-surface)**, which
owns the §2 flag matrix. This mirrors how F1 shipped `--scan`'s existence and deferred
its full validation to F5. F3's acceptance specifies the exclusivity *outcome*
(non-zero exit, no partition counts) as observable contract; F5 owns where in the parse
pipeline the rejection fires.

**Considered and rejected:** a precedence order (e.g. `--lcov` > `--reuse-coverage` >
`--cov-cmd`) — rejected because silently ignoring a passed flag contradicts the tool's
fail-loud contract.
