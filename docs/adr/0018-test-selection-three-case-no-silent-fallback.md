# `--test-contexts` declares three outcomes; disagreeing inputs hard-error

**Status:** accepted

The original implementation returned `None` whenever the context db held no named
test for a line, and silently ran the full suite. That conflated three different
states, one of which is damaging.

| Outcome | Meaning | Response |
|---|---|---|
| `narrowed` | named tests cover the line | run only those node IDs |
| `static` | matched only by the empty (whole-run) context — import-time code no single test owns | run the full test set verbatim, tallied separately |
| `line-absent` / `file-absent` | the db cannot account for the line | **abort, exit 2** |

**Why case 3 is an error and not a fallback.** Selected sites are LCOV-covered *by
construction* — the coverage gate runs before selection. So a db miss can only be an
input defect: a stale db, a path-format mismatch, or coverage recorded in a
subprocess `--cov-context` cannot see. Never "uncovered code". Silently falling back
degraded *every* mutant to a full-suite run — the exact opposite of the flag's
purpose — while still exiting 0.

**Why not a warning line.** mutate4py is agent-first: agents see the `Mutation
Report` block and the exit code, nothing else. A stdout warning is invisible to
them. For the same reason the `Test selection: narrowed <n>, static <k>` tally lives
*inside* the report block.

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
