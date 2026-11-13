# One single-session ctrace Measurement per run; code mutation scores with unit tests only

**Status:** accepted

A scored run first runs one Measurement: one pytest session in the Project
environment, with the run's `--pytest-args`, under coverage.py's `ctrace` core.
The session starts coverage through its API before pytest or any project code is
imported, so lines run while conftests and plugins load are recorded under the
Empty context (`""`). A plugin switches to a context per test, so one session
gives every test its own context. It covers every target of the run: a directory
batch is measured once, not once per file.

The session's data gives three things, read from the same coverage data so they
can never disagree:

- **The Baseline**: the session's wall time, the base of every Mutant's timeout
  (`TimeoutPolicy` in `_test_dispatch.py`).
- **The Coverage gate**: a line is covered iff any context reached it, Empty
  context included. This is the line-only rule (ADR 0007), unchanged.
- **The Test map**: the named tests that reached each line, which the Mutant
  dispatch uses to pick tests (the selection rules are in ADR 0018).

The per-Mutant overhead is the wall time minus the summed test durations, floored
at 0. It replaces the `--collect-only` probe that ADR 0020 describes, and it is
printed once per run.

**Unit tests only.** Code mutation scores with the unit tests alone. Component
tests, integration tests and acceptance features are not part of the Measurement
or of any Mutant run; a run's test set is the `--pytest-args` its caller passes.
In this repo the unit tests take about 17 s in one ctrace session.

**The core is forced, and read back.** The session runs with `COVERAGE_CORE=ctrace`
and coverage's own config file is not read (`config_file=False`), so a user's
`core = sysmon` or dynamic-context setting cannot leak in. Inherited
`COVERAGE_PROCESS_START`, `COVERAGE_RCFILE` and `COV_CORE_*` variables are dropped
from the session environment. The effective core is read back from coverage.py
after start-up, not assumed. `pytrace` is accepted with a report note: correct,
but slower. `sysmon` is refused: a run whose effective core is `sysmon` exits 2
and names the fix (`COVERAGE_CORE=ctrace`; check that nothing in the Project
environment overrides it or restarts coverage, and that coverage is 7.10 or newer
with its C extension installed there).

**Scope.** coverage.py measures only the run's Mutation target files, so test
files and acceptance helpers never enter the data. pytest-cov, when installed, is
neutralised with its own disable option.

**The no-flag path.** A run given none of `--cov-cmd`, `--lcov` or
`--reuse-coverage` takes its Coverage gate from the Measurement, and never reads
`coverage.lcov` (ADR 0007's default path is superseded here). A failing suite
stops the run before any Mutant and names the failing node ids; a suite that
collects nothing keeps the no-tests hint (ADR 0018). A run given a coverage flag
keeps its behaviour: the flag supplies the covered lines, and the Baseline still
comes from the Measurement.

## Rejected alternatives

- **sysmon.** On this repo's 2,087 function-body lines, its line map agrees with
  the isolated build on 122, against 1,982 for ctrace, because it drops every
  context after the first to reach a line. It is refused, not used.
- **The isolated build (ADR 0021).** One pytest process per test. It is much
  slower, and a cold cache costs about 16 minutes (AGENTS.md, `test-context-db`).
- **pytest-cov's `--cov-context=test`.** It inherits the user's config and core
  choice, and it suffixes contexts by phase, so one test's lines split across
  several context names.
- **Sharding the Measurement.** Unneeded once scoring is unit-only, and it adds
  empty-shard and collection-mismatch failure modes.
- **Component tests in code mutation.** With them the session took about 337 s
  instead of 17 s, and in-process pipeline tests joined the code-mutation gate.

**Do not "fix" these back.** Each rejected option was measured against this
repo's line map or its wall time. A session that reads back `sysmon` is a usage
error, not a fallback to `sysmon` or to `coverage.lcov`.
