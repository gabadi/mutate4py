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

**Why case 3 is an error and not a fallback.** Selected sites are covered *by
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

**Batch exit code is the worst per-file code**, severity `2 > 1 > 3 > 0`, not a boolean
collapse — otherwise a case-3 abort in one file is indistinguishable from an
ordinary failure in another. A failing file contributes its code without stopping
the batch. 3 = a scored run finished with at least one unaccepted survivor (ADR 0026).

**One db serves a whole batch.** Generate a single combined `.coverage` spanning
every workspace member; a per-member db would make members disagree about shared
source lines, which the three-case model then turns into a loud abort.

**Note:** this ADR originally recorded that `--test-contexts` forces serial
execution. It no longer does — narrowing composes with parallel Workers.

**Amendment (issue #96): the Measurement is a selection source.** With no
`--test-contexts` db, selection reads the same-run Measurement's coverage index,
so the run prints `Test selection: narrowed <n>, static <k>` with no `degraded`
tally. The Measurement never degrades a Site, so the `degraded` tally and its
`Warning:` line appear only on a `--test-contexts` run. Its outcomes map onto the
table above: a line reached by named tests is `narrowed`; a line reached only by
the whole-run context is `static`. A line the Measurement holds no context for is
`uncovered`: it runs the full test set and is tallied `static`, rather than
aborting. The abort stays reserved for the db's `line-absent` and `file-absent`.

**Amendment (issue #97): a Survivor is confirmed before it counts.** Narrowing runs
a Mutant with only the tests that reached its line, and a narrowed list can miss a
killing test: one that reads state a covering test left behind (a memoised body)
reaches no line of the Site, so no covering list names it. Such a Mutant survives
the narrowed run and would be reported as a Survivor though the full suite kills it.
So every Survivor of a non-accepted Site is re-run with the full test set, in a fresh
interpreter through the subprocess executor, under the full-set timeout, and counts
as a Survivor only if it survives that run too. A kill, or a timeout, under the full
set folds into `killed` (ADR 0011).

- **The orchestrator confirms, serial and parallel alike.** Workers return `survived`
  and the orchestrator confirms serially on its own copy of the file, spliced and
  restored as the serial loop splices it. One path gives both run shapes one verdict.
- **Accepted-equivalent Sites are not confirmed.** Their line carries an equivalent
  marker, so the Survivor is accepted by design and a full run would buy nothing.
- **A fresh interpreter, not the forking executor.** The confirmation exists to rule
  out state leaking between runs; a forked child shares the primed parent's imports,
  and a memoised body read from that parent is the very state to avoid.
- **Visible in the report.** The `Time:` line carries `confirmation .. (n run, k
  killed)`, and the `Executor:` line says how the Mutants ran (`forking (fresh import
  N)`, or `subprocess (<reason>)` for a whole-run fallback).

**Rejected: widen the narrowed list instead.** A covering list is derived from the
lines each test reaches, so a test that matters only through state it reads cannot be
named by it; widening it means running the full set for every Mutant, which is the
cost narrowing exists to avoid. Confirming only the few Survivors keeps narrowing for
the Mutants that die early.

## Addendum (issue #89)

`--test-contexts` is removed in 0.3.0, along with the db it read. Selection reads only
the same-run Measurement's Test map (ADR 0027), so the outcomes narrow to two:
`narrowed` (named tests reach the line, so only those run) and `static` (only the
whole-run context reaches it, so the full test set runs). The `under-listed` outcome
and the disagreement hard-error go with the db: they policed inputs built apart from
the run, and one Measurement has no second source to disagree with. The db-only aborts
(`line-absent`, `file-absent`) go too. The `no-tests-collected` / `usage-error` abort
(exit 2) stays, because it guards a pytest run that exercised nothing.

Survivor confirmation (amendment #97) is what keeps narrowing and swap mode honest. A
Survivor of a non-accepted Site is re-run with the full test set through the subprocess
executor (ADR 0028), and counts only if it survives that run too. A narrowed list cannot
name a test that matters only through state it reads, so this re-run is the step that
catches it.

## Amended: a Mutant can cause exit 4 or 5 (0.3.1)

Case 4 read pytest exit 4 or 5 as a defect in the pytest argv, always. That is wrong for
one cause: a Mutant that breaks a module at import time. When a conftest imports that
module, the conftest fails to load and pytest exits 4. The Mutant is the cause, and
the Mutant is killed. In 0.3.0 the run stopped with exit 2 instead.

The exit code cannot tell the two causes apart. So the run asks the original code, with a
Control run. It applies to exit 4 and exit 5 alike.

- **The Control run.** When a Mutant ends in exit 4 or 5, the run restores the original
  source and runs the same pytest argv once, under the same timeout, through the same
  Executor. If tests run, the argv is good and the Mutant caused the exit: the Mutant is
  `killed`. Tests ran only if pytest exited 0 or 1 (all passed, or a test failed). Any
  other end shows nothing about the argv: exit 4 or 5 again, a timeout, or `errored`.
  Then the argv is the suspect and the run aborts with exit 2, as case 4 always did. A
  run that proves nothing about the argv must not turn a failure into a kill.
- **The abort says what the Control run gave.** The message names the Mutant's own exit,
  then says that a Control run of the same pytest args on the original code ran, and how
  it ended: in exit 4 or 5 too (the args are the defect), in a timeout, or `errored`. A
  timeout or `errored` shows nothing of the args, so the message says it did not show
  whether the args or the Mutant caused the exit. Without that, a Control run that timed
  out told the user to check `--pytest-args` for an argv that was fine.
- **`errored`.** An Executor reports `errored` for a pytest that ended with no result:
  exit 2 (interrupted) or 3 (internal error), any other exit code, a signal, or a process
  that did not start. Before 0.3.1 the Executors reported these as `killed`, so one Control
  run ended by a signal looked like proof that tests ran. It cleared a bad argv for the
  rest of the run, and every later exit 4 was scored `killed`: the false win this case
  exists to stop. A Mutant that ends `errored` is still a kill (ADR 0011): the run folds
  it into `killed` before it tallies.
- **One Control run per argv.** Once a Control run has run tests, its argv is cleared
  for the rest of the run. A later Mutant that ends in exit 4 or 5 with that argv is
  killed with no new Control run. A Control run that ran no test is not remembered,
  because the run aborts on it. The serial loop and Survivor confirmation each keep their
  own record. A parallel run keeps one record for all its Workers: the argv is the same in
  every Worker tree.
- **The Control run is not counted as a Mutant.** It is not a Mutant, so the `Time:` line
  does not time it and the `Executor:` line does not count it. The run tells the Executor
  that a dispatch is a Control run (the `control` flag of `Executor.run`, which a Worker
  carries in its request). A forking Executor runs it but leaves it out of its mode
  counts, so the three counts add up to the number of Mutants that ran.

**The timing dependence on `--no-fork` (0.3.0).** A node id from the Measurement is
relative to pytest's rootdir. Mutants run from the working directory. When the two
differ, every narrowed Mutant names a file pytest cannot find. Such a Mutant ended
either in exit 4 (the abort) or in the Mutant timeout, which is scored `killed`
(ADR 0011). Which one came first depended on whether pytest started before the
timeout. The same project gave an abort on one run and a run of silent kills on the
next. The Control run alone would not fix this: it must stay a dynamic proof, and a
timeout proves nothing.

So the plan now checks the node ids before any Mutant runs. For a narrowed Site, the
file part of every node id must exist under the working directory. If one does not,
the run raises the case 4 error at once, on every Executor and under any timeout. The
message names the node id and says to run mutate4py from the pytest rootdir.

**Rejected: drop exit 4 from the abort.** An argv that names a path that does not exist
is a real defect, and exit 4 is how pytest reports it. Without the abort, every Mutant
would be scored `killed` while nothing tested it: the false win this case exists to stop.

**Rejected: tell the cause from pytest's output.** Matching `ImportError while loading
conftest` in the output ties the rule to pytest's wording and to one failure shape. The
Control run asks the question that matters, whether this argv runs tests on the original
code, and gives the same answer for every cause.
