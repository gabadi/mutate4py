# Test-context db: isolated per-test coverage.py sessions, then `coverage combine`

**Status:** accepted

`--test-contexts` (ADR 0018) reads a pre-built coverage.py context db. Nothing in
mutate4py builds that db today; a user runs their own `pytest --cov-context=test`
and points `--test-contexts` at the result. That single-session approach is
unsound.

## The bug

Verified directly against this project's own pinned coverage.py (7.13.5, per
`uv.lock`) on Python 3.14.5 (`.python-version`), in two independent forms:

1. Bare coverage.py API, no pytest involved: one `Coverage()` session,
   `switch_context()` between three calls to the same function that all touch
   one line. Querying the `arc` table for that line's context IDs returns only
   the FIRST context (`test_a`) — `test_b` and `test_c` are silently absent.
2. Real `pytest --cov-context=test --cov-branch`, one shared session, against
   `tests/fixtures/overlapping_coverage/` (two tests, `test_from_a` and
   `test_from_b`, that both call `shared()`). Read back through this project's
   own reader — `TestContextDB.tests_for_line()` in
   `src/mutate4py/_test_selection.py`, the exact code `--test-contexts` uses —
   the shared line's `narrowed` outcome lists only ONE of the two covering
   tests. Pinned down as a regression test:
   `tests/test_test_context_build.py::test_single_shared_session_under_lists_covering_tests`.

Order-dependent (reproduced with the test order reversed) and independent of
pytest-cov's own machinery (repro 1 bypasses it entirely calling coverage.py
directly) — a coverage.py collector session attributes a line or arc to only
the first dynamic context that touches it, full stop.

**Why this is worse than a db miss.** ADR 0018's three-case model (`narrowed` /
`static` / hard-error) already catches a db that can't account for a line at
all. This bug produces a fourth, silent case: a `narrowed` outcome that looks
completely valid but under-lists which tests actually cover the mutant's line.
A test that would have killed the mutant never runs, and the mutant survives —
the opposite of a loud, catchable failure, and exactly the failure mode ADR
0018 was written to rule out for db misses.

## The decision

Build the db from N isolated coverage.py sessions instead of one shared
session: run each test alone under its own `coverage run` process, with its
own static `--context=<node id>` and its own `--data-file`, then merge every
per-test file with `coverage combine`.

`src/mutate4py/_test_context_build.py`, `build_test_context_db()`, is the
seam: given a list of pytest node IDs and a `cwd`, it returns the path to a
combined db. It has no CLI wiring yet — deciding which tests to run per
target, and any parallelism, is #50's scope, not this one's.

Verified fix, same fixture:
`tests/test_test_context_build.py::test_isolated_session_build_narrows_to_every_covering_test`
builds the db this way and confirms the shared line's `narrowed` outcome
lists BOTH tests, and that each test's own private line still narrows to just
that one test.

Static per-process `--context` also sidesteps a second, independent hazard:
coverage.py warns that dynamic contexts — what `switch_context()`, and so
`--cov-context=test`, use under the hood — aren't fully supported under the
`sysmon` core added in newer Python/coverage.py releases. A static context
naming an entire single-test process has nothing to switch, so that hazard
doesn't apply here at all.

**Cost: slow, deliberately.** One `pytest` startup per test instead of one
shared collection pass. Acceptable for what this proves; #50 is expected to
make that tradeoff explicit at the CLI level (which tests, how many workers)
rather than hide it.

## Rejected alternative: single combined `--cov-context=test` session

The obvious approach — `pytest --cov-context=test` once, covering every test
in one collector run — is what ADR 0018 assumed the db-building side would
look like; its `_DISAGREEMENT_HINTS` text in `_test_dispatch.py` still
recommends it. That hint is now stale; it is not rewritten here because
touching selection/dispatch wiring is #50's scope, not this one's.

Rejected because it silently drops coverage attribution as described above,
and there is no coverage.py or pytest-cov flag that makes a single
dynamic-context session attribute a shared line to more than the first
context that reaches it — confirmed via coverage.py's own `Coverage()` /
`switch_context()` API directly, not only through pytest-cov's wrapping of
it.

## Note

This ADR does not change `TestContextDB` or the three-case classifier (ADR
0018) — both already read a `coverage combine`d db correctly regardless of
how it was produced. It only replaces the missing *build* step.

**Update (issue #69):** the read path did need to change after all — a user
who points `--test-contexts` at their own single-session `.coverage` (not at
a db this ADR's build produced) hits the exact bug diagnosed above, and
nothing said so; the run reported `narrowed N, static 0` as if the db were
sound. ADR 0018 now records a fourth Selection outcome, `under-listed`, that
`TestContextDB.tests_for_line()` returns instead of `narrowed` whenever a
line's covering tests include one recorded by a dynamic (`switch_context`)
context — see ADR 0018 for the detection rule and why it's per-line, not
whole-db. `_DISAGREEMENT_HINTS` and the `--test-contexts` CLI help no longer
recommend the single shared `--cov-context=test` session this ADR rejected.
