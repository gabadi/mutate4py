# The serial run-loop path prints no `Mutation workers` line and no worker token

**Status:** accepted (premise revised)
**Superseded in part by:** ADR 0013 / ADR 0015 (§9 reopened — `--max-workers` and
parallelism are restored). The serial-path observations below remain correct; the
original "parallelism removed entirely / `--max-workers` is a usage error" premise is
**withdrawn**.
**Amended by:** ADR 0019 (single execution model) — see amendment appended below.
**Feature:** F4 (run-loop) · **Spec:** §7, §8, §9 [PY]

mutate4go ships two execution paths — `runMutationsSerial` and
`runMutationsParallel` (copy-the-project-tree-per-worker) — selected per run by
`--max-workers <= 1 || len(sites) <= 1` (`runner.go:319`). **F4 implements only the
serial path.** This ADR records the observable consequences of the serial path in
F4's output so they are not mistaken for an oversight.

> **Context note (post-reopening).** This ADR was first written under spec §9's
> "parallelism removed" stance. That stance was reversed: `--max-workers` is restored
> (ADR 0013) and the parallel engine is **F6**, using a `uv`-provisioned
> clone-per-worker model (ADR 0015) — *not* mutate4go's unsound tree-copy+`cwd`
> model. What survives unchanged is everything below about the **serial** path, which
> is still exactly what F4 ships and still the path taken whenever
> `--max-workers <= 1` or there is a single site.

## The serial path (what F4 ports)

F4 implements upstream's `runMutationsSerial` only: one file on disk, one mutant at a
time — apply → write → run test under timeout → classify → restore — in stable site
(line, column) order. `runMutationsParallel`, `copyProject`, and the worker-root
machinery are **not** in F4 (they are F6, re-grounded on `uv` clone-per-worker).

## Output tokens on the serial path

> **F6 amendment (see ADR 0015 resolution 7).** Item 1 below was first written for the
> F4 case where `--max-workers` is unset/0. F6 chose **upstream-verbatim** printing of
> the header line, so the `Mutation workers:` line is **no longer unconditionally
> absent on the serial path** — it prints whenever `--max-workers > 0`, *even when the
> run executes serially* (`--max-workers 1`, or any `--max-workers` clamped to a single
> selected site). Item 1 is rescoped accordingly. Item 2 (no `worker-<k>` token) stays
> correct: the token is unique to the true parallel path.

1. **`Mutation workers: <n>` header line — conditional on `--max-workers > 0`, not on
   the path.** When `--max-workers` is unset/0 (F4's default case) the serial header is
   exactly the seven count lines (`Mutation run` / Total / Covered / Uncovered /
   Changed / `Manifest exists` / Selected) plus the conditional warning line — **no
   workers line**. But a serial run with `--max-workers > 0` (e.g. `--max-workers 1`)
   **does** print `Mutation workers: <n>`, matching upstream `runner.go:614`
   (`if options.MaxWorkers > 0`). The line tracks the flag, not the execution path.
2. **No `worker-<k>` token in the per-mutant line — on any serial run.** Upstream's
   parallel path prints `[i/total] worker-<k> <status> …` (`runner.go:425`); the serial
   loop has no such token at all (`runner.go:346`). F4's per-mutant line stays
   `[i/total] <status> line <L> <desc>: <functionID>` **even when a serial run prints
   the `Mutation workers:` header** — there is no worker to attribute serially.

The `worker-<k>` token **returns on the parallel path** (F6, workers ≥ 2 AND sites ≥ 2);
the `Mutation workers:` line returns whenever `--max-workers > 0`. Every other §8 string
is reproduced verbatim on both paths.

## Flag boundary

`--max-workers` is not handled in F4 at all: F4 consumes already-parsed options and
runs the serial loop. Parsing/validating `--max-workers` is **F5** (ADR 0013/0014);
acting on a value `>= 2` to take the parallel path is **F6** (ADR 0015). (The original
text here called a passed `--max-workers` a "usage error" — that is withdrawn; it is a
valid flag.)

## Amendment (2026-08-10) — re-scoped by ADR 0019

The output-token contract above (the two numbered items) is **unchanged and
authoritative**. What ADR 0019 withdraws, by re-scoping rather than by editing
anything above, is the assumption that "serial" and "parallel" are two separate
execution engines chosen once per run: after that ADR, serial is the one-Worker
case of a single Worker-dispatch mechanism, and which test-executor a Worker holds
is orthogonal to the token rules recorded here. Full reasoning in ADR 0019.
