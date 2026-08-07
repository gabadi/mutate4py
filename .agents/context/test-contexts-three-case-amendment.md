# `--test-contexts` three-case amendment — implementation context

```
derived-from: e1d61362bfa2e54dadbd38fa2724d23d5f0a75fe
covers: src/mutate4py/_test_selection.py, src/mutate4py/_runner.py, tests/test_test_selection.py, tests/test_runner.py, features/test-selection.feature, docs/adr/*, docs/spec.md, CONTEXT.md
```

Meta/process documentation for a later reviewer round — not a product file.
Convention used below: every non-quoted claim is prefixed `(inferred)`. Anything
unprefixed is either a direct quote from the issue #27 decision comment (the
source contract) or a direct quote/restatement of a repo file I read.

## What the source contract required

Quoted from the issue #27 decision comment:

> **Design policy: no silent fallbacks.** Every Mutant gets exactly one declared
> outcome. Disagreeing inputs are a hard error, never a silent repair.

> | 1 | Context db names tests covering the line | Run only those tests (**narrowed**) |
> | 2 | Line executes only at import time … | Run the **full `--test-command`**, as the stated rule |
> | 3 | Db has nothing for an LCOV-covered line, or the file path misses entirely | **Exit 2** with an actionable message |

> New line **inside the `Mutation Report` block**, present whenever
> `--test-contexts` is on: `Test selection: narrowed N, static K`

## Decisions I made (the three the task asked me to record)

### 1. Exact exit-2 message wording

Composed from two pieces. `_build_mutant_command` raises
`TestSelectionError(f"{abs_source_path}:{site.line}: {hint}")`; `run_mutations`
catches it and prints to **stderr**:

```
error: test-context db disagrees with coverage: <abs_source_path>:<line>: <hint>
```

The two hints (`_DISAGREEMENT_HINTS` in `src/mutate4py/_runner.py`) are:

- `line-absent` → `line is LCOV-covered but absent from the test-context db (stale db: regenerate it with pytest --cov-context=test)`
- `file-absent` → `file is not in the test-context db at all (path-format mismatch, or its coverage was recorded in a subprocess)`

(inferred) `_build_mutant_command` branches on `"narrowed"` and `"static"`
explicitly and **raises on everything else**, with a third hint
(`unrecognized selection outcome <outcome>`) covering any outcome string the two
modules disagree about. So "no silent fallback" is structural: there is no path
from an unexpected outcome to a full-suite run that the report would then
miscount as narrowed.

(inferred) I split case 3 into two *outcomes* rather than one, because the db
lookup is the only place that can tell a stale db from a path mismatch, and the
task asked to distinguish them "where you can tell". The contract says "The API
must be split into three outcomes"; I shipped four outcomes covering three
*cases*. (inferred) I judged that a refinement rather than a contradiction, but
it is the one place I deliberately did not take the contract literally — flagged
again under Gaps.

(inferred) Exit code 2 is returned from `run_mutations`; `_dispatch_single_file`
in `__main__.py` already does `sys.exit(run_mutations(...))`, so no change to
`__main__.py` was needed for the single-file path.

### 2. Where case 3 is checked

In `_run_mutation_loop` (`src/mutate4py/_runner.py`), at the **top of each
per-site iteration**, before `apply_mutant` and before the file write:

```python
for i, site in enumerate(selected_sites, 1):
    # Built before the splice so a db miss aborts with the source untouched.
    cmd, selection = _build_mutant_command(...)
```

(inferred) Consequence: on abort the file on disk holds the *previous* site's
mutant (or the clean source, if the first site aborts) — never a partially
written one. `_execute_mutations` wraps the loop in `try/finally` so
`_finalize_source` runs on the abort path exactly as on the success path
(restore `clean_source`, re-embed the manifest, remove `.mutate4py.bak`). The
`TestSelectionError` then propagates out of `_execute_mutations` to
`run_mutations`, which owns the message and the `return 2`.

(inferred) I chose `try/finally` + propagation over catching inside
`_execute_mutations` because the latter duplicated the six-argument
`_finalize_source` call; `run_mutations` already had a `try/…/finally` for
`test_ctx_db.close()`, so the `except` clause slots in with no new nesting.

(inferred) Precedent followed: the parallel-error path already calls
`_finalize_source` before returning non-zero, and ADR 0016 makes that write
idempotent, so an aborted run leaves no spurious `tested_at` churn.

### 3. `Test selection:` line placement and format

Printed by `_print_mutation_report`, immediately after the `Uncovered:` line and
before any `Survivors:` block:

```
Mutation Report
===============
Killed: <k>
Survived: <s>
Uncovered: <u>
Test selection: narrowed <n>, static <k>

Survivors:
  …
```

Gated on `selection_counts is not None`; `_run_mutation_loop` returns `None` for
that tally when `test_ctx_db is None`, and `_execute_mutations` passes `None` on
the parallel path. (inferred) So a run without `--test-contexts` is byte-for-byte
unchanged, which matters because `docs/spec.md` §8 is a [PORT] "reproduce
strings verbatim" section. (inferred) I picked the post-`Uncovered:` position
because the three lines above it are the run's tallies and this is a fourth
tally; putting it after `Survivors:` would have buried it under a variable-length
block, which is worse for `awk`-style agent parsing.

## API shape chosen in `_test_selection.py`

`TestContextDB.tests_for_line(source_path, line) -> tuple[str, list[str]]`, with
outcome one of `"narrowed"` / `"static"` / `"line-absent"` / `"file-absent"`.

(inferred) Plain outcome strings rather than an `enum` or a dataclass, because
`_runner.py`/`_cmd.py` already model the per-mutant verdict as bare strings
(`"killed"`, `"timeout"`, `"survived"`) keyed into a dict, and AGENTS.md-adjacent
conventions favor "no premature abstraction". A `_classify(tests, static)` helper
folds the matched contexts into an outcome, shared by the bits-mode and arcs-mode
helpers so the two modes cannot drift.

(inferred) Both helpers now *keep* the empty-context row instead of `continue`-ing
past it: bits mode sets a `static` flag when the empty context's numbits contains
the line; arcs mode compares `len(tests) < len(contexts)` after filtering. A named
test always wins over the empty context when both matched the line — asserted by
a test in each mode.

## Self-review dispositions (standards axis)

(inferred) A standards-axis review of the diff raised five points. Accepted and
fixed:

- **Glossary drift** — CONTEXT.md says "Use the glossary terms below in issue
  titles, **test names**, and proposals; don't drift to synonyms." The code and
  tests said "db miss" while CONTEXT.md's new entry says *Selection
  disagreement*. Renamed `_DB_MISS_HINTS` → `_DISAGREEMENT_HINTS`, the four
  `*_db_miss_*` test names → `*_disagreement_*`, and the two comments. No
  residual "db miss" vocabulary remains in `src/` or `tests/`.
- **Oblique derivation** — the arcs path inferred staticness numerically
  (`len(tests) < len(contexts)`). Now `any(not c for c in contexts)`, which
  states the condition directly and mirrors the bits path's explicit branch.
- **Placeholder-case inconsistency** — `<N>, <K>` in the ADR/feature vs
  `<n>, <k>` in spec/CONTEXT. Normalized to `<n>, <k>` everywhere.

Declined, recorded as Gaps 13–15 below:

- **Primitive Obsession** on the four outcome strings.
- **Redundant nullable channel** (`test_ctx_db is None` encoded twice).
- **Two error protocols in one function** in `_execute_mutations`.

(inferred) ADR 0018's format follows ADR 0016's shape (numbered heading, bullet
metadata, Context/Decision/Consequences) rather than ADR 0017's prose-metadata
shape; both precedents exist in `docs/adr/`, so no change was made.

## Self-review dispositions (spec axis)

(inferred) A spec-axis review against the issue #27 contract confirmed all five
deliverables land. It raised six points. Accepted and fixed:

- **Silent-fallback hole in `_build_mutant_command`.** The original branch order
  was `if outcome in <hints>` → `if outcome == "static"` → *else narrowed*, so any
  unrecognized outcome (or `"narrowed"` with empty `node_ids`) produced
  `f"{test_command} "` — a full-suite run tallied as narrowed, which is precisely
  the silent repair the spec bans ("Disagreeing inputs are a hard error, never a
  silent repair"). `_classify` made it unreachable, but only incidentally.
  Restructured so narrowed and static are the only non-raising branches, with a
  fallback hint for unrecognized outcomes, plus
  `test_build_mutant_command_unrecognized_outcome_raises`.
- **Stale docstring.** `run_mutations` still said `Returns exit code (0 or 1)`;
  it now documents 0, 1, and 2.

Declined / already recorded:

- Directory & union-batch exit-code collapse — Gap 1, spec-fenced.
- `Examples:` table alignment in the feature file — already fixed before the
  review landed.
- The `_finalize_source`-in-`finally` restructure and the arcs `line <= 0` guard's
  hint — Gaps 17 and 18 below.

## Verification performed

- `uv run pytest tests/` → **704 passed** (was 702 before my two extra
  boundary tests; 26 in `tests/test_test_selection.py`).
- `just check lint format-check test crap dry manifest` → all six ✓.
- `just check` (full) → `acceptance` ✗, see Gaps.
- Mutation, `src/mutate4py/_test_selection.py`, full suite, `--mutate-all`:
  **19 killed, 0 survived**.
- Mutation, `src/mutate4py/_runner.py`, full suite, `--lines` scoped to the
  changed regions (186–250, 294–390, 775–790): **22 killed, 0 survived**.
- `uv run mutate4py src/ --check-manifest` → all current; the two edited files'
  manifests were stripped before editing and regenerated with
  `--update-manifest`, per AGENTS.md.

## Gaps

Exhaustive. Anything here is a known hole, not a surprise.

1. **The directory / union-batch dispatch collapses exit 2 to exit 1.**
   `_run_files_and_exit` (`src/mutate4py/__main__.py`) does
   `if _run_on_file(...) != 0: exit_code = 1`. So on `just mutate src/` — the
   *primary* dogfooding path — a case-3 abort surfaces as exit **1**,
   indistinguishable from survivors, defeating "Exit codes are the contract" for
   multi-file runs. The stderr message still prints and the run still stops for
   that file, but the remaining files are still processed. I did **not** fix
   this: the task says "do not touch … the union-batch dispatch path in
   `__main__.py`", and `_run_files_and_exit` is literally that function.
   (inferred) Recommended fix if the reviewer wants it: let the aggregator take
   `max(exit_code, rc)` (or special-case 2 as terminal) — a one-line change, but
   it changes directory-run semantics for every mode, so it wants its own
   decision.
2. **The `acceptance` gate could not be run.** `gherkin-parser` is broken in this
   environment: it fails with
   `java.io.FileNotFoundException: Could not locate aps/cli/gherkin_parser.bb …`
   for **every** feature file, including untouched ones (verified against
   `features/ci.feature`), and `acceptance/generated/` does not exist in this
   worktree. (inferred) Pre-existing environmental breakage, not caused by this
   change — but it means `features/test-selection.feature` was never machine-parsed,
   so a Gherkin syntax error in my edit would not have been caught. It parses by
   eye only.
3. **`features/test-selection.feature` has no step implementations and never
   did.** `acceptance/run_acceptance.sh`'s `STEPS_MAP` has no `test-selection`
   entry, so the harness prints `SKIP: no steps module for test-selection`. I
   added new scenarios (cases 1/2/3, the report line) that are therefore
   **documentation only, not executed**. I did **not** create a
   `test-selection_qa.feature` sibling (the task said not to invent one unless
   clearly required) and I did **not** wire a steps module — that would be a
   substantially larger piece of work. (inferred) The three cases *are* covered by
   unit tests in `tests/test_runner.py` end-to-end through `run_mutations`, so the
   behavior is tested; only the Gherkin layer is not.
4. **Four outcomes, not three.** As noted above, the contract says "split into
   three outcomes"; I shipped `line-absent` + `file-absent` as separate outcomes
   to satisfy the "distinguish stale db from path mismatch" requirement. If the
   reviewer wants literal three, collapse them and lose the hint distinction.
5. **`--test-contexts` + `--max-workers >= 2` still silently forces serial.**
   Explicitly out of scope; untouched. (inferred) Worth naming because it is the
   same "silent repair" family this ADR rejects — I recorded it as still-open in
   ADR 0018's Consequences rather than fixing it.
6. **Workspace / union-batch *scoping* of `--test-contexts` untouched.**
   `_workspace.py` and the union dispatch path are unmodified, per the task's
   scope fence. (inferred) The open question — which db applies to which root in a
   multi-root run — is unaddressed and unrecorded anywhere except issue #27.
7. **The dogfooding `.coverage` db under-attributes lines, and I did not chase
   why.** Querying the repo's own fresh `.coverage` (regenerated by `just check
   test`) for `_test_selection.py:91` returns exactly **one** covering test, though
   many tests execute that line. Consequence: `just mutate <file>` (which passes
   `--test-contexts .coverage`) under-narrows and reported 6 survivors on
   `_test_selection.py` where a full-suite run reports 0. (inferred) This is a
   property of the repo's coverage-context setup (branch/arcs mode is active —
   `line_bits` is empty for that file), not of this change, and it predates it.
   (inferred) But it materially weakens `just mutate` as a hardening signal, and I
   only worked around it by running the mutation gates with the full suite instead.
   Not investigated further; not filed as an issue.
8. **No test asserts the exact full stderr string.** `tests/test_runner.py`
   asserts the prefix `error: test-context db disagrees with coverage` plus
   `<path>:<line>` plus a hint substring, not the whole sentence. (inferred)
   Deliberate — full-string assertions on prose are brittle — but it means a
   reworded hint would not fail a test.
9. **The abort path re-embeds the manifest.** On a case-3 abort the manifest is
   re-embedded (via `_finalize_source`) even though the run never completed, so
   `tested_at` can advance on a run that tested nothing. (inferred) I followed the
   existing parallel-error precedent rather than inventing a new rule, and ADR
   0016's structural-equality reuse means it only advances if a hash actually
   changed — but it is a semantic wrinkle nobody has ruled on.
10. **`_classify` is exported in `__all__`.** (inferred) Added so the seam is
    addressable, consistent with `_numbits_to_lines` / `_strip_context_suffix`
    already being there; it has no direct unit test of its own (covered
    transitively through both helpers).
11. **Two pre-existing survivors in `_test_selection.py` were killed as a side
    effect.** I added `test_tests_for_line_arc_mode_rejects_line_zero_even_when_an_arc_carries_it`
    and `test_tests_for_line_arc_mode_matches_line_one` to close the `line <= 0`
    boundary. (inferred) Mild scope creep — the guard is pre-existing code — but it
    took the file to a clean 0-survivor mutation score.
13. **Primitive Obsession on the outcome strings (declined).** CONTEXT.md names
    "Selection outcome" a domain concept, but it is four bare strings declared in
    three places: `_classify` returns three of them, `tests_for_line` returns
    `"file-absent"` inline, and `_DISAGREEMENT_HINTS` in `_runner.py` re-declares
    two of them as dict keys — a cross-module coupling with nothing enforcing it.
    (inferred) I kept bare strings because `_cmd.py`/`_runner.py` already model
    the per-mutant verdict the same way (`"killed"`/`"timeout"`/`"survived"`), and
    the repo's conventions favor no premature abstraction. A `Literal` type alias
    exported from `_test_selection.py` would close it cheaply if a reviewer
    disagrees.
14. **The "no context db" fact is encoded twice (declined).**
    `_build_mutant_command` returns `selection=None` when `test_ctx_db is None`,
    and `_run_mutation_loop` independently re-derives the same condition at its
    return (`selection_counts if test_ctx_db is not None else None`). (inferred)
    Left as-is because collapsing them made the type of the tally awkward, but
    the two must stay in sync by hand.
15. **`_execute_mutations` carries two error protocols (declined).** The parallel
    path signals failure by return value (`error_msg`), the serial path by
    exception (`TestSelectionError`), so the function pre-initializes two
    sentinels and wraps both in `try/finally`. (inferred) Unifying them would mean
    touching `_run_parallel_workers`, which the task placed out of scope.
17. **`_finalize_source` now runs in a `finally` wrapping BOTH branches of
    `_execute_mutations`.** (inferred) Previously each branch called it
    separately, so an *unexpected* exception escaping `_run_parallel_workers`
    (i.e. anything other than `WorkerFailureError`/`ParallelRunError`, which it
    catches) left the source unfinalized; it now finalizes. Normal parallel output
    is unchanged and `_workers.py`/`_run_parallel_workers` are untouched, but this
    is a behavior delta on the parallel path that the task did not ask for. It is
    untested — I judged it strictly safer (source restored rather than left
    mutated), but a reviewer who reads "serial-path only" strictly should know.
18. **The arcs-mode `if line <= 0` guard now feeds a case-3 hint that
    misdescribes it.** That pre-existing guard rejects coverage.py's synthetic
    sentinel values, which is a "not a real line number" condition, not a "two
    coverage sources disagree" one — yet it returns `"line-absent"`, so a caller
    would get the *stale-db* hint. (inferred) Unreachable from the run loop, since
    `Site.line` comes from the AST and is always >= 1; reachable only by calling
    `tests_for_line` directly. Not fixed; a distinct outcome for it would add a
    fifth string for a case the runner cannot produce.
19. **No type checker was run.** The repo has no mypy/pyright gate (`just
    check`'s gates are lint, format-check, test, crap, dry, manifest,
    acceptance), so the new `dict[str, int] | None` and `tuple[str, str | None]`
    annotations are unverified by tooling.
