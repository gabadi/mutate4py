# `--max-workers` is restored as a real flag (§9 reopened)

**Status:** accepted
**Feature:** F5 (cli-surface) · **Spec:** §2, §9 (reopened) · **Supersedes the §9
"parallelism removed" stance and the F1-era assumption behind ADR 0012**

The spec's locked decision (§0 row 5, §9) removed `--max-workers` and made passing
it a usage error, on the grounds that mutate4go's parallel model (copy the project
tree, redirect imports via `cwd`/`sys.path`) is unsound in Python — PEP 660 editable
installs write an **absolute** path to the original source that no `cwd` override
beats (mutmut v3 #456). That reasoning about *mutate4go's mechanism* is correct, but
the conclusion (drop the flag) was overturned by the user: **`--max-workers` must
stay a real working flag, matching upstream mutate4go.**

## Decision

- `--max-workers` is a **supported flag again**, parsed and validated in F5 exactly
  as upstream `internal/cli/cli.go` does (positive-int value; see ADR 0014).
- The flag is no longer a usage error on sight. The only combination that errors is
  the one upstream also rejects: combining `--max-workers` with `--scan` or
  `--update-manifest` (those two modes do no execution, so a worker count is
  meaningless there — `cli.go:88,94`).
- The **parallel execution** the flag enables is a separate feature, **F6
  (parallel-workers)**, because mutate4go's tree-copy model cannot be ported
  verbatim — F6 uses a Python-correct `uv`-provisioned clone-per-worker mechanism
  (see ADR 0015). F5 owns only the flag surface and validation, and passes the
  parsed worker count through to the run dispatcher.

## Why F5 validates but does not execute

This mirrors the established slicing: F1 shipped `--scan`'s *existence* and deferred
its full validation/wiring to F5; F2 shipped thin `--update-manifest` and deferred
its validation wiring to F5. By the same boundary, F5 ships `--max-workers`'s parse
+ validation + pass-through, and F6 acts on it. Keeping execution out of F5 keeps the
"front door" feature small and shippable, and lets the substantial worker engine be
specified and built as its own slice.

## Consequence for §9 and ADR 0012 (reconciled in this change)

`spec.md §0` (row 5) and `§9` previously read "parallelism removed," and ADR 0012
was written under that assumption. To keep the documentation accurate as a current
reference (not just historically banner-ed), this change **updates them now** rather
than deferring:

- **spec.md §0 row 5 + §9** — rewritten: `--max-workers` restored; serial by default,
  parallel via `uv`-provisioned clone-per-worker; the failure analysis of
  mutate4go's tree-copy model is kept (it is *why* `uv` clone-per-worker is the
  answer). The §9 prose may be *expanded* with worker-engine specifics during F6
  grilling, but no longer asserts the false "removed."
- **ADR 0012** — its serial-path observations are preserved; its "parallelism removed
  / `--max-workers` is a usage error" premise is withdrawn with a "superseded in part
  by 0013/0015" note.

What genuinely remains for F6: the worker-engine *implementation* decisions (copy
granularity, exact `uv` commands, worker-dir convention, `.mutate4py.bak`
interaction) — captured as open questions in ADR 0015, not contract text asserting a
falsehood.

**Considered and rejected:** keeping the flag removed (a usage error) — rejected by
explicit user direction for upstream parity. Treating `--max-workers` as an unknown
option — rejected: it loses the upstream parse/validation shape and the deliberate
scan/update-manifest exclusion.
