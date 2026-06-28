# The serial run-loop path prints no `Mutation workers` line and no worker token

**Status:** accepted (premise revised)
**Superseded in part by:** ADR 0013 / ADR 0015 (§9 reopened — `--max-workers` and
parallelism are restored). The serial-path observations below remain correct; the
original "parallelism removed entirely / `--max-workers` is a usage error" premise is
**withdrawn**.
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

## Two output tokens are absent on the serial path

1. **No `Mutation workers: <n>` header line.** Upstream prints it on the parallel
   path; F4's serial header is exactly the seven count lines (`Mutation run` / Total /
   Covered / Uncovered / Changed / `Manifest exists` / Selected) plus the conditional
   warning line.
2. **No `worker-<k>` token in the per-mutant line.** Upstream's parallel path prints
   `[i/total] worker-<k> <status> …` (`runner.go:425`); the serial path omits it
   (`runner.go:346`). F4's per-mutant line is `[i/total] <status> line <L> <desc>:
   <functionID>`.

Both tokens **return on the parallel path** (F6); their absence is specific to the
serial path, not a global removal. Every other §8 string is reproduced verbatim on
both paths.

## Flag boundary

`--max-workers` is not handled in F4 at all: F4 consumes already-parsed options and
runs the serial loop. Parsing/validating `--max-workers` is **F5** (ADR 0013/0014);
acting on a value `>= 2` to take the parallel path is **F6** (ADR 0015). (The original
text here called a passed `--max-workers` a "usage error" — that is withdrawn; it is a
valid flag.)
