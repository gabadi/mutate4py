# `--test-contexts` declares three outcomes; disagreeing inputs hard-error

**Status:** accepted

The original implementation returned `None` whenever the context db held no named
test for a line, and silently ran the full suite. That conflated three different
states, one of which is damaging.

| Outcome | Meaning | Response |
|---|---|---|
| `narrowed` | named tests cover the line, every one recorded by a static (isolated-session) context | run only those node IDs |
| `under-listed` | named tests cover the line, but at least one was recorded by a *dynamic* (`pytest --cov-context=test`) context — a method proven (ADR 0021) to silently drop covering tests, so the list can't be trusted complete | run the full test set verbatim, tallied apart from `static` (issue #69) |
| `static` | matched only by the empty (whole-run) context — import-time code no single test owns | run the full test set verbatim, tallied separately |
| `line-absent` / `file-absent` | the db cannot account for the line | **abort, exit 2** |
| `no-tests-collected` / `usage-error` | dispatch built a command (pytest exit 5 / 4), but pytest ran no test at all for the Mutant | **abort, exit 2** |

**Why case 3 is an error and not a fallback.** Selected sites are LCOV-covered *by
construction* — the coverage gate runs before selection. So a db miss can only be an
input defect: a stale db, a path-format mismatch, or coverage recorded in a
subprocess `--cov-context` cannot see. Never "uncovered code". Silently falling back
degraded *every* mutant to a full-suite run — the exact opposite of the flag's
purpose — while still exiting 0.

**Why case 4 is the same error, one step later (issue #55).** Case 3 catches a db
that names no test *before* dispatch. But a db (or a `--pytest-args` filter) can
name tests that pytest then fails to run — a renamed/deleted test node ID, a `-k`
filter that deselects the narrowed selection, a node-ID path format pytest can't
resolve. Verified empirically: a stale node ID surfaces as pytest exit 4 ("not
found: ... no tests ran"), a deselecting filter as exit 5 ("no tests were
collected"). Either way pytest exercised nothing, so classifying by exit code alone
— `run_argv`'s original behaviour, zero survives, everything else is `killed` —
scored the Mutant `killed` while nothing tested it: the same silent false win case 3
exists to prevent, reached through the run instead of before it. `run_argv` now
classifies these two exit codes as a distinct status the run loop raises on, not
tallies, before the file-restore machinery both cases already share (`_finalize_source`
runs in the caller's `finally` block regardless of which case aborts). Both Executor
backends collapsed exit codes the same way — `run_argv`'s subprocess path and the
forking executor's `_wait_for_child` each had their own `0 → survived else killed`
— so the classification now lives once, in a shared `classify_exit_code`, and both
backends call it.

**Why not a warning line.** mutate4py is agent-first: agents see the `Mutation
Report` block and the exit code, nothing else. A stdout warning is invisible to
them. For the same reason the `Test selection: narrowed <n>, static <k>, degraded
<m>` tally, and the `under-listed`-caused `Warning:` line beneath it, both live
*inside* the report block.

**`under-listed`: a fourth, silent case ADR 0018's three cases didn't cover
(issue #69).** `narrowed` / `static` / hard-error assumed a db that names tests
completely or not at all. ADR 0021 proved a third shape: a db built from a
single shared `--cov-context=test` collector session names tests *some* of the
time — coverage.py attributes an arc or line to only the first dynamic context
that reaches it, so a line two tests cover can resolve to `narrowed` with just
one of them. That result is not a db miss (case 3) and not import-time code
(case 2); it looks exactly like a trustworthy `narrowed` while quietly running
too little. A killing test never runs, and the Mutant is scored `survived`.

**Detection is provenance-based, not a count.** There is no way to recover
*how many* tests should have been named — the missing attribution leaves no
trace in the db a heuristic on context counts could reconstruct (confirmed
empirically: a real 37-test/12-context repro shows some multi-test lines
correctly listing 2+ tests and others silently collapsed to 1, with no
structural difference between a collapsed line and a genuinely single-owner
one). What *is* recoverable, unconditionally: pytest-cov's
`TestContextPlugin.switch_context()` names every dynamic context
`"<node id>|setup"` / `"|run"` / `"|teardown"` — a suffix mutate4py's own
isolated-session build (`_test_context_build.py`, static `coverage run
--context=<node id>`) never produces. That suffix alone proves a context came
from the method ADR 0021 rejected, and per that ADR "there is no coverage.py or
pytest-cov flag that makes a single dynamic-context session attribute a shared
line to more than the first context that reaches it" — so *any* line naming
even one dynamic context is untrustworthy, not just the ones that happen to
collide. `_is_dynamic_context()` in `_test_selection.py` is the check;
`TestContextDB.tests_for_line()` returns `"under-listed"` instead of
`"narrowed"` whenever it fires.

**Response: fall back to static, not abort.** Unlike case 3 (no safe fallback
exists for a line the db can't account for at all), running the full test set
is always correct for an under-listed line — it's what `static` already does,
just for a different reason. Reusing that dispatch keeps `_build_mutant_args`
simple and, per issue #69's acceptance criteria, actually resolves the
`_test_context_cache.py` repro's 5 false survivors to `killed` rather than
merely aborting the run. The report tallies it apart from genuine `static`
sites (`degraded`, not folded into either existing bucket) precisely so the
summary can't claim `static 0`/imply a clean `narrowed` run while some Sites
were rejected — see `_DISAGREEMENT_HINTS` and the CLI help for `--test-contexts`,
both of which stopped recommending the single-shared-session build as part of
this same change.

**Rejected: flag every dynamically-built db unconditionally, whole-db-wide,
with no per-line check.** Cheaper (one query at db-open time instead of one
per line), and arguably still correct given the "any dynamic context taints
its line" rule already degrades every `narrowed` outcome such a db could ever
produce. Rejected anyway: a combined db can mix isolated-session files (static,
trustworthy) with dynamic-session files (untrustworthy) for different targets
in the same batch (ADR 0018's "one db serves a whole batch"), and a whole-db
flag would wrongly degrade the sound half too. The per-line check subsumes the
whole-db case for free — a db that is *entirely* dynamic degrades every line
anyway — without this false-positive risk.

**Prior art** (verified against primary sources): mutmut, Stryker and PIT all give
an unattributable mutant a distinct visible status; none silently falls back.
Stryker runs the full suite for "static" mutants — case 2 exactly. mutmut
hard-errors when its test↔mutant mapping breaks — case 3.

**Batch exit code is the worst per-file code**, severity `2 > 1 > 0`, not a boolean
collapse — otherwise a case-3 abort in one file is indistinguishable from an
ordinary failure in another. A failing file contributes its code without stopping
the batch.

**One db serves a whole batch.** Generate a single combined `.coverage` spanning
every workspace member; a per-member db would make members disagree about shared
source lines, which the three-case model then turns into a loud abort.

**Note:** this ADR originally recorded that `--test-contexts` forces serial
execution. It no longer does — narrowing composes with parallel Workers.
