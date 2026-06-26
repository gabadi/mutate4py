# `--reuse-coverage` reads `coverage.lcov`; the gate is line-coverage only

**Status:** accepted
**Feature:** F3 (coverage-gate) · **Spec:** §6

Two coverage decisions baked into the F3 contract and costly to change later.

## Default path — `coverage.lcov` at repo root

`--reuse-coverage` reads LCOV from a fixed default path, **`coverage.lcov`** at the
current working directory. When `--reuse-coverage` is given and no file exists there,
the tool emits a hard usage error and exits non-zero, telling the user to generate
coverage once — matching `mutate4go`'s behavior when its coverprofile is missing.

**Why `coverage.lcov` and not `lcov.info`.** Spec §6 left this "Open" and *guessed*
`lcov.info` "is the crap4py/coverage.py convention." That guess is wrong on evidence:
`coverage.py`'s own `coverage lcov` subcommand writes to **`coverage.lcov`** by default
(`-o OUTFILE … Defaults to 'coverage.lcov'`, coverage.py 7.x). Since coverage.py is the
spec-named LCOV emitter for this Python tool, its zero-config default *is* the standard
the project should meet, so a user who runs `coverage lcov` then `mutate4py <file>
--reuse-coverage` works with no path flag. The same-author Python sibling (`crap4py`)
also emits `coverage.lcov` in its worktrees, confirming the convention. This ADR
**supersedes the spec §6 `lcov.info` open note.**

**Divergence from the mirror.** `mutate4js` (ADR 0005) uses `coverage/lcov.info` — the
JS reporter (Vitest/c8/Jest) convention, *not* coverage.py's. mutate4py deliberately
diverges per-language: we follow the Python emitter's default, not the JS one. The
default is a constant, not a tunable; changing it later would silently break user
workflows, which is why it is pinned here.

## Line-coverage-only gate

A mutation site is **covered** iff its line has an LCOV `DA:<line>,<count>` record with
`count > 0`; a site whose line is absent from LCOV or has `DA` `count == 0` is
**uncovered**. **Branch data (`BRDA`) is deliberately ignored.** This ports
`mutate4go`'s line gate (a site is covered iff its line sits in a segment with
`Count > 0`) and is correct on purpose: branch-gating would suppress exactly the
boundary survivors (`>` vs `>=`) the tool exists to surface. A future reader seeing
`BRDA` parsed-then-discarded (or never parsed) should know it is intentional.

## Parser reuse is the *pattern*, not the *target*

The spec says "reuse crap4py's LCOV parser." crap4py's `coverage.py` parser reads
**`BRDA`** records (it computes *branch* coverage per function) — the wrong target for
this line gate. So mutate4py reuses crap4py's *shape* — the line-by-line
`SF:` / `end_of_record` state machine and the suffix `SF`-matcher — but parses
**`DA`** records instead of `BRDA`. Path reconciliation is suffix-based (one path is a
path-suffix of the other), porting `mutate4go`'s suffix matching to bridge
absolute-vs-relative `SF:` forms.
