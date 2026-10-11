# Survivors fail the scored run and stay in the Manifest

**Status:** accepted

A scored run that leaves an unaccepted survivor exits 3. `--allow-survivors` turns
that into 0, for runs that measure rather than gate. Batch severity is `2 > 1 > 3 > 0`.
A module-level survivor also exits 3.

Each Function unit's Manifest entry carries a `score` block: `score` (`killed`,
`survived`, `uncovered`), `survivors` (unaccepted `{line, desc}`) and `accepted`
(`{line, desc, reason}`). `killed` includes timeouts (ADR 0011), and
`survived == len(survivors) + len(accepted)`. The fields are kept while the unit hash
is unchanged and dropped when it changes. A function is rescored only when the run
selected every covered Site in it; a function with no covered Site is rescored only by
a full-file run. A narrowed run that finds a recorded survivor's Site uncovered keeps the function's old block. An aborted run rescores nothing. A full-file run whose coverage misses
a survivor's line clears it: on an explicit full run, coverage is the truth.

`--check-manifest` exits 1 while any function records a survivor, and checks this
before the `source_sha256` fast path, so a matching footer hash cannot hide one.
Survivor-carrying functions count as changed, so the next default run retries them.

An equivalent is accepted by `# mutate4py: equivalent <reason>` on the mutated line.
It accepts every survived Site on that line, so to accept one of two Sites, split the
line. An empty reason is exit 2. The comment is hash-neutral (ADR 0005).
Removing or rewording a marker makes its function not current, like a survivor.
A function without `score` is Unscored: `--check-manifest` judges it on hashes and
prints `(unscored)`.

Accepted consequences:
- After a hash-changing edit, `--update-manifest` drops that function's survivors. The
  function becomes Unscored and `--check-manifest` passes on hashes, the same skip that
  already applies to changed functions.
- A 0.1.4 Manifest gains scores only for functions a run fully selects. A default
  differential run selects nothing unchanged, so one `--mutate-all` run scores the file.
- A module-level survivor exits 3 but is not recorded: it has no function entry, so
  `--check-manifest` cannot see it.

**Do not "fix" these back.** The gate is on by default, because a gate that is off
gates nothing. Survivors stay in the Manifest so `--check-manifest` sees them without a
run. The marker sits in the source, so it moves with the code.

Rejected alternatives:
- Opt-in `--fail-on-survivor`: a gate's default must gate.
- A hand-edited `accepted` list as the source of truth: it is dropped when the function
  changes, and the reason sits far from the code.
- Auto-accepting by category from `.agents/references/equivalent-mutants.md`: that file
  is prose and records no verdict per Site.
- `--require-scored`: not needed yet.
- Per-Site merging of partial runs: a partly selected function's score cannot be known,
  so it is skipped.
