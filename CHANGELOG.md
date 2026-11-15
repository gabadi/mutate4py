# Changelog

## 0.3.1

### Fixed

- A Mutant that breaks a module at import time is killed. In 0.3.0 it stopped the run with
  exit 2 (`pytest ran no test for a Mutant ... exit 4`), when a conftest imported the module.
  When a Mutant ends in pytest exit 4 or 5, the run now makes a Control run: the same pytest
  argv on the original code. If tests run there, the Mutant broke the run and is killed. If
  the Control run runs no test or times out, the argv is the defect and the run still aborts
  with exit 2 (ADR 0018 amendment).
- A node id from another pytest rootdir now aborts the run before any Mutant runs, on every
  Executor. In 0.3.0 the result depended on timing: the run aborted, or each Mutant timed out
  and was scored killed. The message names the node id and says to run mutate4py from the
  pytest rootdir.

## 0.3.0

The run measures coverage itself and re-scores only what changed (spec #89). Decisions
are in [`docs/adr/`](docs/adr/): ADR 0027 (the Measurement), ADR 0028 (executors),
ADR 0029 (the tests digest and skip rule).

### Removed flags

Each flag below is refused with exit 2 and a message naming it, `<flag> removed in 0.3.0: <reason>`.
Remove them from scripts and CI.

- `--cov-cmd`: the run measures coverage itself (the Measurement, ADR 0027). No replacement.
- `--lcov`: the run measures coverage itself; no `lcov.info` is read or written. No replacement.
- `--reuse-coverage`: each scored run takes its Measurement; a rerun with nothing changed skips it. No replacement.
- `--test-contexts`: selection reads the run's own Measurement and its Test map; there is no db to pass. No replacement.
- `--build-test-contexts`: no test-context db is built. No replacement.
- `--since-last-run`: a default run already re-scores only the changed functions. Drop the flag.
- `--lines`: edit a function to re-score it.
- `--mutate-all`: a run scores every changed or Unscored function itself. A run with no Manifest scores every function (an uncovered one gets an `uncovered` score). Drop the flag.

### Changed

- Coverage comes from one Measurement per scored run: one pytest session of the unit tests
  under coverage.py, which also gives the Baseline and the Test map (ADR 0027).
- New runtime dependency: coverage.py, `coverage>=7.10`.
- `--min-timeout` default is 5.0 s, up from 1.0 s. `--timeout-factor` stays at 10.
- The per-Mutant overhead is the Measurement's wall time minus the summed durations of its
  tests. No `--collect-only` pass runs. The overhead hint fires at half of the Measurement's wall.
- A default run re-scores only changed functions. A function is changed when its Unit hash
  or its tests digest differs, it is Unscored, or it records Survivors and has no digest yet
  (ADR 0029). A default run also scores every Unscored function, including one no covered Site reaches (spec #115). A run with no Manifest scores every function (an uncovered one gets an `uncovered` score); `--mutate-all` is removed.
- Unchanged functions are skipped even when they record Survivors. Those Survivors print under
  `Recorded survivors (function unchanged, not re-run):` and still count toward exit 3 (0 with `--allow-survivors`).
- Test selection has two outcomes, `narrowed` and `static`, read from the Measurement's Test map
  (ADR 0018). The report prints `Test selection: narrowed <n>, static <k>`.
- Every non-accepted Survivor is re-run with the full test set, in a fresh interpreter through the
  subprocess executor. It counts only if it survives that run too (ADR 0018 amendment #97, ADR 0028).
- Executors: the forking executor runs Mutants by fresh import or swap mode (ADR 0028); the
  `Executor:` line of the report says how each Mutant ran.
- `--check-manifest` checks unit hashes, recorded Survivors and equivalent markers. It runs no
  test, so it does not check tests digests.

### Migration

- Delete the seven removed flags from scripts and CI. The run needs no prior coverage step, and
  `--pytest-args` still passes through to pytest.
- A Survivor recorded on an unchanged function now fails the run (exit 3) until it is killed or
  accepted with `# mutate4py: equivalent <reason>`.
- A 0.2.x Manifest entry with Survivors and no tests digest is retried once.
- To keep the 1.0 s floor, pass `--min-timeout 1.0`.
