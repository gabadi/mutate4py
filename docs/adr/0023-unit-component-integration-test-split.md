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
Where the chain's measurement *ends* was revised twice later — see the session-5
and session-6 addenda below. It now closes at `test-unit`.
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

## Addendum: the coverage measurement ends at `test-component` (session 5)

The append chain described above ran `test-unit` → `test-component` →
`test-integration`, with `test-integration` emitting `lcov.info` and applying
`--cov-fail-under=90`. That made `integration` the nominal owner of both
metrics while contributing nothing to either. It is **coverage-blind**:
`COVERAGE_PROCESS_START` is unset, so a spawned interpreter's execution is
invisible to the parent's `.coverage` — the addendum above already established
the same fact for named contexts.

Measured on this tree:

- `lcov.info` built from `unit+component` is **byte-identical** to one built
  from `unit+component+integration` (`diff -q` → identical).
- `check_context_deselection.py` reports the **same 257 named contexts** with
  and without the `integration` append.

So `test-integration` left the measurement, and `test-component` took over
emitting `lcov.info` and owning the threshold. `test-integration` still appends
(`--cov-append`, no report) so that wiring up subprocess coverage later lands
its data in the same file instead of needing this plumbing rebuilt. **The
measurement moved once more in session 6 — see the addendum below; the evidence
above is unaffected, only where the chain closes changed.**

The argument made here for keeping `component` *inside* the measurement was
that dropping to `unit`-only fails `crap` outright: twelve functions exceed the
CRAP cap of 6 — worst `collect_test_node_ids` 42.0,
`ForkingExecutor.run_isolated_coverage_session` 20.0,
`WorkerProcessExecutor.prime` 20.0 — and total coverage drops 95.5% → 91.0%.
That argument was **conceded and is superseded**; the session-6 addendum
records why, and what happened to those twelve functions.

## Addendum: the measurement is `unit`-only (session 6)

The session-5 argument above reasons from a label, not from the tests' nature.
These tests were `unit`-marked only until this ADR split them out for gate
speed — but this ADR's own definition of `component` is *real subprocess/fork
execution via mutate4py's own Executor*, distinguished from `integration` only
by being in-process and therefore coverage-**visible**. Visibility is an
implementation accident of where the work happens to run. It is not a reason to
count integration-nature work in a metric named for units.

**`test-unit` now emits `lcov.info` and owns `--cov-fail-under`.**
`test-component` and `test-integration` both append silently. `crap` and
`mutate-sample` read `lcov.info` and so require `test-unit` alone.
`context-deselection` is the exception: it reads `.coverage` and needs every
context a Mutant run could narrow against, and `MUTATE_PYTEST_ARGS` excludes
only `integration` — so it still requires `test-unit` **and** `test-component`.
The two files now serve different purposes: `lcov.info` is a unit-only snapshot
taken when `test-unit` ends; `.coverage` keeps accumulating.

The twelve over-cap functions were fixed, not deferred, and not by mocking
`os.fork`. The arithmetic makes that unnecessary: CRAP is
`CC² × (1 − cov)³ + CC`, so at 0% coverage a CC-2 function scores exactly 6 and
clears the cap while remaining entirely unit-untested. The fix for a
fork/spawn wrapper is therefore to extract until the wrapper itself is CC ≤ 2,
which is what `AGENTS.md` already prescribes for boundary code. Every
extraction produced a pure, unit-tested helper:
`node_ids_from_collect_result`, `worker_server_argv`/`encode_request`/
`_shutdown_process`, `parse_worker_argv`/`worker_environ_updates`,
`ForkingExecutor._fork_and_wait` (which also deduplicated the fork/wait pair
`run` and `run_isolated_coverage_session` had each spelled out),
`run_isolated_session`, `measure_baseline_and_overhead`,
`_prime_worker_executor`/`_close_worker_executor`/`_drop_one_result_if_injected`,
and `overhead_info`. Two guard tests that never reach a fork were reclassified
`component` → `unit` alongside them.

Unit-only coverage came out at **92.63%**, up from the 91.0% session 5 measured,
because those helpers are now unit-tested. `--cov-fail-under` stays at **90**:
the number is a floor, its meaning is unchanged by the narrower basis, and 3pp
of headroom is a healthier margin than the 1pp it had before — raising it to
match the current reading would just turn every future refactor into a
threshold fight.

`crap4py` offers no baseline or allowlist mechanism (`--max-crap N` and
`--fragment`, an include-only path filter, are the whole surface), so this
could not have been staged through configuration; the code had to move.

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
