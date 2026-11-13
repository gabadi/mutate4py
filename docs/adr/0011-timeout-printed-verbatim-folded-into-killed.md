# `timeout` is visible per-mutant and invisible in the report — both deliberate

**Status:** accepted

A timed-out mutant prints `timeout` (not `killed`) on its per-mutant progress line,
so a hung or pathologically slow mutant stays distinguishable in the live log from
one a test genuinely caught. The final report folds it in: `Killed` is
`killed + timeout`, and there is **no `Timeout:` line** — a mutant that didn't
complete within `timeout-factor × baseline` didn't survive.

**A change that either hides the per-mutant `timeout` token or adds a `Timeout:`
report line breaks this contract.**

**Amendment (issue #96): the bound is no longer `timeout-factor × baseline`.** A
Mutant's timeout is `max(--min-timeout, --timeout-factor × budget) + Per-Mutant
overhead`. The budget is the summed measured duration of the tests the Mutant
runs, plus the largest fixture setup among their files: a narrowed Mutant budgets
its own covering tests, and a static Mutant budgets the full test set. The
Per-Mutant overhead, the wall time spent outside the tests, is added so a narrowed
Mutant with few tests is not timed out by fixed cost. The contract above is
unchanged: the `timeout` token stays visible and no `Timeout:` line is added.

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
