# A per-function tests digest decides whether a scored function is still proven

**Status:** accepted

A scored function stays proven while the tests that can reach it do not change, and
its proof is invalidated by a change to any of those tests and by nothing else
(issue #88). Each scored Function unit's Manifest entry carries a `tests_digest`
beside its `score` block, and the changed-function rule reads it.

## Digest inputs

A function's digest is a SHA-256 over sorted `(relpath, content SHA-256)` pairs of:

- **The test files that reach its covered Site lines.** The Measurement (ADR 0027)
  records which tests reached each line, so the input set comes from what the
  tests loaded, not from directory shape. A function with a covered Site line that
  is Static (reached only under the Empty context) takes every collected test
  file, since no single test owns that line.
- **The conftests of those test files**: every registered `conftest.py` in the test
  file's directory or an ancestor.
- **The support files**, a run-level set shared by every function: modules under a
  test root that a test imported and that are neither test files nor conftests
  (factories, helpers, sibling-directory modules), the pytest table of
  `pyproject.toml` (the rest of that file is ignored), the pytest ini file, and
  `uv.lock`. A test module whose tests the run's arguments deselected (`-m`, `-k`)
  is a test file, not a support file: pytest imports it to collect it, but none of
  its tests runs, so under unit-only scoring an edit to a component-only test file
  re-scores nothing (#110).

Coverage's own config is not an input: the Measurement runs with
`config_file=False` and pytest-cov disabled.

## Site lines only

Reach is taken over a function's covered **Site** lines, not over every line of its
span. A `def` or decorator line runs when the module is imported or, for a lazy
import, under whichever test imports it first. Counting those lines would let an
edit to a test that merely imports a module re-score everything it defines, and
would pull every test file in through the Empty context. A test that reaches only
the definition line is not an input.

## Skip rule

A function is re-scored when any of these hold:

1. it is Unscored;
2. its Unit hash changed (ADR 0005);
3. its stored digest is present and differs from the fresh one;
4. an Accepted equivalent lost its marker (ADR 0026);
5. it has Survivors and no stored digest.

Otherwise it is skipped, **even when it records Survivors**. This replaces ADR
0026's "Survivor-carrying functions count as changed": a Survivor is a verdict on a
function against the tests that reach it, and when neither moved, a rerun can only
repeat it. A skipped function's recorded Survivors are not re-confirmed. They print
on their own `Recorded survivors (not re-run):` block, apart from the run's own
`Survivors:`, and count toward the exit code like any unaccepted Survivor: exit 3,
or 0 with `--allow-survivors`. A run with no Manifest re-scores everything (`--mutate-all` was removed by spec #115).

The digests are taken from the Measurement, so a Differential rerun selects a
function whose digest moved exactly as it selects a hash-changed one.

## Adoption

An entry with no stored digest and no Survivors **adopts** the fresh digest on the
first run that sees it, with no re-score (the ADR 0026 precedent for 0.1.4
Manifests). An entry with Survivors and no digest fails condition 5, so a 0.2.x
entry with Survivors is re-scored once, gains its digest with the new score, and is
skipped from then on. There is no upgrade-specific code: condition 5 is the whole
rule.

`--update-manifest` carries a digest by the hash rule (kept while the hash is
unchanged, dropped when it changes) and never computes one. `--check-manifest`
checks hashes, recorded Survivors and equivalent markers, and says so in its
`--help`; a stale digest does not fail it, because no Measurement exists to
recompute it.

## Accepted gaps

- **A helper outside every test root is not an input.** A module a test imports from
  outside every test root (and outside the Mutation target files) is neither
  measured nor digested. Editing it re-scores nothing. The alternative is guessing
  which files "matter" from the import graph, the pattern ADR 0022 rejected; the
  acceptance helpers under `acceptance/` are the case that decided it, because
  acceptance mutation is a separate gate (ADR 0027).
- **A support file re-scores every function.** The support set is run-level: the
  digest cannot tell which test imports a factory without guessing. An edit to a
  factory or a sibling-directory helper under a test root re-scores every scored
  function, which is sound and costs a rerun.
- **A 0.2.x writer drops the field.** An older mutate4py rewriting a Manifest
  discards `tests_digest`, so those entries adopt again, or re-score once when they
  record Survivors.
- **State outside the repository** (environment variables, network, the clock, an
  installed package other than through `uv.lock`) is not an input.

Rejected alternatives:

- **One digest over the whole tests tree** (the consumer's `.harden-proof.json`):
  every test edit invalidates every proof, the problem issue #88 reports.
- **A digest over every line in the function's span:** def and decorator lines
  make an import-only test an input.
- **Guessing helpers from directory shape:** ADR 0022's three narrow rules each
  missed a differently-shaped helper.
- **Always retrying a function with Survivors:** a fix loop on a branch re-ran every
  Survivor on every edit, whatever the edit.
- **An upgrade branch that re-scores every 0.2.x entry once:** a clean entry has
  nothing to re-prove, and its digest costs one read.

**Do not "fix" these back.** Each gap is a deliberate trade of a rerun for a guess.

## Addendum (issue #89): the tests fingerprint and the no-change rerun

The per-function rule above decides which functions a rerun re-scores. A coarser
check decides whether a rerun runs at all: when nothing it depends on has changed,
the rerun skips its Measurement and every Mutant.

**Fingerprint.** A scored run records a `tests_fingerprint` in the Manifest: a SHA-256
over the test inputs its `--pytest-args` collect (the test files and conftests under
each collection root, the pytest config and `uv.lock`), the pytest args, the Python
version and the mutate4py version. It is computed after the `.bak` restore, with the
Manifest footer stripped. Only a run that writes at least one score block records it;
a run that scores nothing keeps the stored fingerprint. `--update-manifest` keeps the
stored fingerprint and `--check-manifest` ignores it.

**Skip.** An invocation skips its Measurement and every Mutant when every target it
names (one file, or every file of a batch) has a Manifest that is readable and
parseable, has no `.bak` beside it, records the fresh fingerprint, has an unchanged
source body, has a score and a digest for every function, and has its accepted
Survivors' equivalent markers intact. A run with no Manifest never skips (`--mutate-all` was removed by spec #115). The decision is taken
once per invocation, before any Measurement: one target that blocks it blocks the
whole batch, since a batch shares one Measurement.

A skipped run prints the skipped Measurement line, the `Recorded survivors (not re-run):`
block of the stored Manifests, and a Time line of zero. It writes nothing and prints no
Mutation Report, because it scored nothing. Its exit code follows the survivor rule
above: 3 for an unaccepted recorded Survivor, or 0 with `--allow-survivors`.

Rejected alternatives:

- **Printing a Mutation Report from the stored totals on a skipped run:** the numbers
  would read as this run's score when this run scored nothing.
- **Skipping per target inside a batch:** the batch's one Measurement is shared, so a
  partial skip would still measure the files it was meant to skip.

**Do not "fix" these back.** The fingerprint's inputs and the all-or-nothing batch rule
are what make a skip safe; narrowing either lets a stale proof read as current.

## Amendment: spec #115

A default run scores every Unscored function, including one that no covered Site
reaches. Such a function is not skipped: its Sites are tallied Uncovered and its `score`
block is written with `uncovered` set. Unscored means no `score` block, or no stored
entry; `unscored_functions` agrees with `is_unscored`. A function whose Unit hash or
tests digest moved is scored the same way, so an edited function no test reaches is scored
by the edit run and the next run takes the skip. A function that has a stored score, an
unchanged hash and no covered Site is still skipped by the rule above. This amends ADR
0026's line that a function with no covered Site is rescored only by a full-file run.

`--mutate-all` is removed and refused with exit 2. Its full re-score is now a run with no
Manifest: that run is full-file and scores every function, an uncovered one with an `uncovered` score.
