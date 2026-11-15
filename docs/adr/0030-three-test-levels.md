# Three test levels: unit, system, acceptance

**Status:** accepted (2026-11-15, issue #122)

The suite has three levels. The marker and the gate decide the level, not the
directory: `tests/` holds unit and system tests side by side.

- **`unit`** tests run in-process and are fully isolated. Only they are measured.
  `test-unit` writes `lcov.info`, which the CRAP gate reads, and the Measurement of
  a scored run (ADR 0027) takes only the unit tests. A Mutant only a system test
  kills is a Survivor until a unit test kills it (ADR 0023, issue #89).
- **`system`** tests run real processes: a fork server, worker servers, nested
  pytest sessions, or a spawned interpreter. `test-system` runs them under
  pytest-xdist (`-n auto`), which assumes the tests are independent of one another.
  A failure only under xdist is a shared-state or ordering bug to fix; the gate is
  not run serially to hide it. The gate passes `--no-cov`, so it writes no coverage
  data.
- **Acceptance** runs the Gherkin features through `just acceptance`.

Every test carries exactly one of `unit` or `system` as its own decorator.
`tests/conftest.py` fails a test that has neither or both.

`test-system` runs with `-p no:tach`. The tach pytest plugin is fork-unsafe (it
deadlocks a forked child; see `_FORK_UNSAFE_PLUGIN_MODULES`) and re-runs impact
analysis on every subprocess spawn (issue #26). A test that needs tach loaded gets
it from its own nested session, which does not inherit the outer run's
`-p no:tach`. Such a test fails, rather than passing vacuously, if that session
cannot load tach.

## Rejected alternatives

- **Keep four layers (unit, component, integration, acceptance).** The split
  between `component` and `integration` was drawn at the coverage-context and
  interpreter boundaries (ADR 0023). Issue #89 removed the dynamic context, and both
  markers are now outside code mutation and outside any gate that reads coverage.
  The distinction decides only which gate runs a test, so a single `system` gate
  covers both with no loss.
- **Two levels, unit and acceptance.** Acceptance drives whole CLI runs and does not
  stand in for the tests that pin the internals of those runs: fork-server parity
  with the subprocess executor, hang recovery (a child that hangs is killed and
  reported), the choice between swap and fresh-import mode, Measurement internals,
  the stored tests digest (ADR 0029), and the Django worker protocol. Moving those
  tests into the unit set would put real processes into the Measurement, which ADR
  0027 measured as a large cost.
- **Keep coverage appends "for later".** The old append chain (`test-unit` →
  `test-component` → `test-integration`) wrote coverage that no gate reads. The CRAP
  gate reads `lcov.info` from `test-unit` alone (issue #89), and the Measurement
  never reads `.coverage` (ADR 0027). Appends nothing reads add a second writer to
  the coverage data. A later gate that needs system coverage can add its own append
  together with its reader.

**Do not "fix" these back.** Each rejected option was measured or traced to a
concrete failure mode above. Reintroducing a coverage append or a second non-unit
marker needs a reader for the data it writes.
