# `timeout` is visible per-mutant and invisible in the report — both deliberate

**Status:** accepted

A timed-out mutant prints `timeout` (not `killed`) on its per-mutant progress line,
so a hung or pathologically slow mutant stays distinguishable in the live log from
one a test genuinely caught. The final report folds it in: `Killed` is
`killed + timeout`, and there is **no `Timeout:` line** — a mutant that didn't
complete within `timeout-factor × baseline` didn't survive.

**A change that either hides the per-mutant `timeout` token or adds a `Timeout:`
report line breaks this contract.**

## The colon asymmetry is intentional

The per-mutant progress line puts a colon before the function id:

```
[3/9] timeout line 12 a > b -> a >= b: func/calc
```

The `Uncovered mutations:` and `Survivors:` lines do **not**:

```
  line 12 a > b -> a >= b func/calc
```

Upstream-exact (`runner.go:346` vs `:622, :644`). Don't normalise them.
