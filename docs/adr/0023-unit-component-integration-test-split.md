# A third test marker, `component`, alongside `unit`/`integration`

**Status:** accepted

Issue #71 reported the `test-unit` gate as slow (95s quoted). Measurement against
a clean CI run put its real cost at 54.94s, and the slowest individual tests
turned out to concentrate in a handful of files: `test_run_mutations_modes.py`,
`test_runner.py`, `test_subprocess_executor.py`, `test_baseline.py`,
`test_dispatch_cli.py`, `test_worker_protocol.py`, `test_executor_composition.py`.
Each of those calls `run_mutations()` / `main()` directly, in-process, against a
real generated source file and a real pytest project on disk — spawning real
subprocess/fork Executor work per call. They are shaped like component tests, not
unit tests, but carried no marker distinguishing them from the ~900 genuinely
fast, fully-isolated tests sharing the same gate.

## Why not just reuse the existing `integration` marker

`integration` already has a narrow, load-bearing meaning (ADR-adjacent, see its
docstring in `pyproject.toml`): a test whose work runs inside a **spawned
interpreter** (via `_run_cli_path`/`_run_cli_in`), so `--cov-context=test` cannot
see it, and it is therefore excluded from `mutate`'s per-Mutant test narrowing.

The slow tests above are not that. They run in the *same* interpreter as the
test session, so `--cov-context=test` sees them fine and they stay eligible for
narrowing — reusing `integration` for them would incorrectly strip that
eligibility. Verified mechanically, not just by reasoning: reclassifying any of
them as `integration` makes `scripts/check_context_deselection.py` (the gate
`context-deselection`, built for issue #54) fail unconditionally, because every
one of them is currently a named context in `.coverage` under the `test-unit`
gate's `-m 'not integration'` filter — moving it to `integration` removes it
from that filter's selection while it is still recorded as the context a Site's
narrowing may pick, exactly the misconfiguration #54 built that gate to catch.

## The decision

A third marker, `component`: real subprocess/fork execution via mutate4py's own
Executor, but in-process and `--cov-context=test`-visible. Every test must carry
exactly one of `unit` / `component` / `integration` as its **own** decorator —
enforced in `tests/conftest.py`, which fails (retroactively, via
`pytest_runtest_makereport`) any test whose own markers (`item.own_markers`, not
`item.iter_markers()`) include none of the three, attaching the test's
just-measured duration and a duration-based suggested marker to that failure.
`own_markers` deliberately excludes a module- or class-level `pytestmark`
default: a default would let a newly-added test silently inherit a category
nobody chose for it, which is the exact thing this gate exists to prevent — so
there is no file-level default anywhere in `tests/`, only per-test decorators.
The suggestion is duration-based and appears only on that failure — never as a
proactive per-test hint — because duration cannot tell `unit` from `integration`
(that distinction is about interpreter/coverage-context boundaries, not speed)
and a live-flaky suggestion is not useful; only the "you must decide" error is
unconditional, decided by whoever writes the test.

`test-unit`'s filter becomes `-m 'not integration and not component'`. A new gate,
`test-component`, runs `-m component`, appending to `test-unit`'s coverage data
exactly as `test-integration` already does — same append chain, extended from two
links to three (`test-unit` → `test-component` → `test-integration`), same reason
(splitting the coverage measurement itself, rather than which gate runs which
tests, would misattribute lines only these tests reach and turn `crap` red, per
ADR-adjacent reasoning already in the justfile for the unit/integration split).
`mutate`'s own `--pytest-args` default is untouched (`-m 'not integration'`):
`component` tests keep their place in per-Mutant narrowing, they only lose their
place in the fast dev-loop gate.

## Migration

All ~1000 existing tests were classified in one pass: any test at or above 0.5s
wall-clock on a measured run became `component`; everything else became `unit`;
tests already marked `integration` were untouched. Applied as an explicit
`@pytest.mark.{unit,component}` decorator on every single test function — no
module-level `pytestmark` default anywhere, per the `own_markers` decision
above.

## Addendum: `context-deselection` root-cause fix (session 3)

The migration above left `just check context-deselection` (issue #54's gate)
failing with violations, initially assumed pre-existing/unrelated. Investigation
found the violations were a direct consequence of this ADR's own migration: it
deliberately left every pre-existing `@pytest.mark.integration` test untouched
(see "Migration" above), but a subset of those tests don't actually match
`integration`'s definition — they call mutate4py's own Executor/orchestration
code (`ForkingExecutor`, `WorkerProcessExecutor`, `build_test_context_db`,
`TestContextDB`, `_prepare_executor`) directly in-process. That's this ADR's
`component` definition, not `integration`.

Fixing only the initially-flagged tests whack-a-moled: coverage.py's
`.coverage` context table is session/order-dependent, so a rebuild after a
partial fix surfaced a *different* set of violations each time (18 → 12 → 2).
The only durable fix was a full static sweep of every `@pytest.mark.integration`
test, using the same spawned-interpreter detection `test_integration_marker_guard.py`
already used (a literal `subprocess.run/Popen/call/check_output/check_call` with
a `sys.executable` arg, or the `_run_cli_path`/`_run_cli_in` helpers). 22 tests
with no such call were reclassified `integration` → `component` (all of
`test_forking_executor.py`'s remaining integration tests, plus tests across
`test_dispatch.py`, `test_executor_composition.py`, `test_executor_selection.py`,
`test_test_collection.py`, `test_test_context_build.py`,
`test_test_context_orchestration.py`, `test_worker_protocol.py`). 2 more in
`test_test_context_build.py` contain a literal spawn only as a fixture-generation
detail inside a nested helper, with the test's actual subject in-process — also
reclassified. 4 tests (`test_dispatch_cli.py` x3, `test_main_cli_flags.py` x1)
were genuinely `integration`-shaped but had an incidental in-process
`mutate4py.__main__.main()` call used only for setup (writing a manifest) before
the real subprocess assertion — fixed by replacing that setup call with the same
subprocess-based `_run_cli_path(..., "--update-manifest")` pattern the rest of
each file already uses, rather than reclassifying them.

`test_integration_marker_guard.py` was widened to accept `@pytest.mark.component`
as well as `@pytest.mark.integration` on any test with a literal interpreter-spawn
call: the guard's real concern (keep spawn cost out of the fast `test-unit` loop)
is equally satisfied by either non-`unit` marker, and the guard predates
`component`'s existence.

**A second, independent bug** was found in `scripts/check_context_deselection.py`
itself: after the sweep above converged, the 56 remaining genuine `integration`
tests have zero overlap with named `.coverage` contexts — fully invisible to
`--cov-context=test`, exactly this ADR's own `integration` definition. The
script's defensive sanity check assumed the opposite: it raised `GateError` if
no `integration`-marked test was visible in `.coverage`, treating that as
evidence of a broken build. That assumption only ever held because the
misclassified tests above accidentally kept some `integration`-marked test
visible; once classification is correct, zero overlap is the gate's own goal,
not a failure signal. The check was backwards and was removed (the correctly-
directioned "unit half missing" check was kept). Its only consumer,
`--integration-pytest-args`/`integration_args`, was removed with it — confirmed
unreferenced elsewhere in the repo.

## Rejected alternatives

- **Repurpose `integration`/`unit` as the only two categories** (redefine
  `integration` to also mean "slow, real execution"). Rejected: breaks
  `context-deselection` deterministically, as shown above — not a hypothetical
  risk.
- **Proactive per-test timing hints on every green run** (e.g. print a
  suggestion for every test whose duration crosses the threshold, marked or not).
  Rejected per explicit direction: noise on every run buries the signal; the
  suggestion belongs attached to the one place a human/model must already stop
  and decide — the missing-marker failure — not scattered across passing output.
- **Module-/class-level `pytestmark` default, read via `item.iter_markers()`.**
  Tried first, then rejected: it let any test added later to an already-migrated
  file inherit that file's default category without anyone deciding it,
  defeating the entire point of a mandatory, per-test, human/model-made call.
