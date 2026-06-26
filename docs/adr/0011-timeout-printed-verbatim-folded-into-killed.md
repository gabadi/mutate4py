# A timed-out mutant prints `timeout` per-line but counts as `Killed` in the report

**Status:** accepted
**Feature:** F4 (run-loop) · **Spec:** §7 (classification), §8 (output)

Spec §7 says a timeout is "counted as killed," and §8 shows a per-mutant `<status>`
token — leaving open whether the live progress line shows `timeout` or `killed`.
Resolved against `mutate4go`, which is unambiguous on both halves.

## Per-mutant progress prints the literal `timeout`

`runMutant` returns three status strings: `"killed"` (non-zero exit), `"timeout"`
(test exceeded the deadline), `"survived"` (zero exit) (`runner.go:464-485`). The
serial loop prints the status **verbatim** in the progress line
(`runner.go:346`):

```
[i/total] <status> line <L> <orig> -> <mutant>: <functionID>
```

So a timed-out mutant prints `[3/9] timeout line 12 a > b -> a >= b: func/calc`.
Printing `timeout` (not `killed`) keeps a hung or pathologically-slow mutant
distinguishable in the live log from one a test genuinely caught — the operator can
see the suite is timing out rather than killing.

## The final report folds `timeout` into `Killed`

`summarize` reports `Killed: counts["killed"] + counts["timeout"]`
(`runner.go:636`). A timed-out mutant did not survive — the suite failed to complete
within `timeout-factor × baseline`, which is a defect signal, so it is tallied as
killed. There is **no `Timeout:` line** in the report; the only report lines are
`Killed`, `Survived`, `Uncovered`, and the conditional `Survivors:` block.

**Net:** `timeout` is visible at the mutant granularity and invisible at the report
granularity — deliberately, on both counts. A future change that either hides the
per-line `timeout` token or adds a `Timeout:` report line would break this contract.

## The colon before `<functionID>`

The per-mutant line, the `Uncovered mutations:` lines, and the `Survivors:` lines all
end in `<desc> <functionID>` — but only the **per-mutant progress** line has a colon
between description and status's payload: `… <desc>: <functionID>` (`runner.go:346`),
whereas the uncovered/survivor lines are `  line <L> <desc> <functionID>` with **no**
colon (`runner.go:622, 644`). This asymmetry is upstream-exact and pinned here because
spec §8 wrote the per-mutant line without the colon; the Gherkin follows upstream.
