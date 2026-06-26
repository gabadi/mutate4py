# The run loop is serial-only: no worker pool, no `Mutation workers` line, no worker token

**Status:** accepted
**Feature:** F4 (run-loop) · **Spec:** §7, §8, §9 [PY]

`mutate4go` ships two execution paths: `runMutationsSerial` and
`runMutationsParallel` (copy-the-project-tree-per-worker), selected by `--max-workers`
(`runner.go:317-327`). Spec §9 [PY] removes parallelism entirely as unsound in Python
(PEP 660 editable installs resolve an absolute path no `cwd`/temp-copy overrides).
This ADR records the **observable** consequences in F4's output, so the omission is
not mistaken for an oversight.

## Only the serial path is ported

F4 implements upstream's `runMutationsSerial` only: one file on disk, one mutant at a
time — apply → write → run test under timeout → classify → restore — in stable site
(line, column) order. `runMutationsParallel`, `copyProject`, `shouldSkipCopy`, and the
worker-root machinery are **not** ported. There is no worker tree, no skip list.

## Two output tokens are removed (the only F4 divergence from §8 strings)

1. **No `Mutation workers: <n>` header line.** Upstream prints it when
   `MaxWorkers > 0` (`runner.go:614`). F4 never prints it — the header is exactly the
   seven count lines (`Mutation run` / Total / Covered / Uncovered / Changed /
   `Manifest exists` / Selected), plus the conditional warning line.
2. **No `worker-<k>` token in the per-mutant line.** Upstream's parallel path prints
   `[i/total] worker-<k> <status> …` (`runner.go:425`); the serial path already omits
   it (`runner.go:346`). F4's per-mutant line is `[i/total] <status> line <L> <desc>:
   <functionID>` with no worker token.

Every other §8 string is reproduced verbatim. Because nothing is copied, there is also
no `--max-workers` flag in F4 at all; the **usage error** for a passed `--max-workers`
is F5's (CLI surface), not F4's — F4 simply has no parallel code path to gate.
