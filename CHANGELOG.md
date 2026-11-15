# Changelog

## 0.3.3

### Fixed

- Survivor confirmation in a parallel run now uses the fork server. The orchestrator builds a
  fork server with the run's prime arguments and confirms a Survivor of a "fresh import" file
  there, as a serial run does. A Survivor of a file that a Worker swaps or runs in its harness
  is confirmed in a fresh interpreter, inside the Worker that ran it, before the Worker closes.
  Before, a parallel run confirmed every Survivor in a new interpreter. Amends ADR 0018.
- A run that aborts writes nothing. The Manifest sidecar is written atomically, and an aborted
  run leaves it as the last finished run wrote it. An embedded Manifest footer is left as it
  was too: an aborted run in embed mode neither adds a footer nor updates one. A failure of a
  parallel Worker counts as an aborted run.
- A Survivor in a class body is recorded in the Manifest, under the class's own entry
  (`class/<Name>`), so `--check-manifest` sees it. Before, it failed the run with exit 3 but
  was not recorded. A class outside a function is now a unit for its own body. Its hash leaves
  out its methods and its nested classes, so an edit to a method does not re-score the class.
  The first run on a file with a class re-scores the class, and `--check-manifest` reports the
  file stale until a run or `--update-manifest` adds the class entries. A Survivor outside every
  function and class is still not recorded; the report now prints each one as `file:line` under
  "Module-level survivors (not recorded in the Manifest):".
- A run started in a directory other than the pytest rootdir no longer aborts. The Measurement
  now exposes its rootdir, and the plan rebases the node ids of a narrowed Mutant from the rootdir
  to the run directory. The timeout is still budgeted on the ids as the Measurement recorded
  them. A node id whose file does not exist still aborts the run with exit 2.
- The tests digest now includes every file that does not end in `.py` under the test folders
  (fixture JSON, golden files, tables). Before, an edit to such a file left a stored proof
  current. The file is shared by every function, so an edit to one re-scores the whole file;
  an edit to a `.py` test still re-scores only the functions it reaches. Hidden files and
  directories and `__pycache__` are not inputs. Amends ADR 0029.

### Changed

- The `Uncovered mutations:` block and the `Uncovered mutation sites:` header count cover the
  run scope: the changed or Unscored functions in a differential run, every function in a full
  run. The block now prints each Site as `file:line` and prints in a differential run too.
  Before, it printed in a full run only, and the count covered every function.

## 0.3.2

### Fixed

- A scored run no longer fails its Measurement with "unrecognized arguments: --no-cov" (exit
  code 4) when the child pytest does not load pytest-cov: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`
  or `--disable-plugin-autoload` with no `-p pytest_cov`, or `-p no:pytest_cov` (#127). The
  same holds for pytest-benchmark's `--benchmark-disable`. mutate4py drops a plugin's switch
  only when its module is importable and the child provably does not load it; whenever the
  session args, `PYTEST_ADDOPTS`, the ini `addopts`, `PYTEST_PLUGINS` or a conftest names the
  plugin, the switch stays, so a project that loads pytest-cov through its ini `addopts` under
  autoload off is still scored (not silently Uncovered). When unsure, the switch is kept. Amends
  ADR 0020.

## 0.3.1

### Fixed

- A fresh worktree of an unchanged checkout now takes the skip. In 0.3.0 the tests digest keyed
  ancestor config files by path up to the filesystem root, so every new worktree rescored. The
  ancestor walk now stops at pytest's inifile (#119). (Added to these notes in 0.3.2.)
- A Mutant that breaks a module at import time is killed. In 0.3.0 it stopped the run with
  exit 2 (`pytest ran no test for a Mutant ... exit 4`), when a conftest imported the module.
  When a Mutant ends in pytest exit 4 or 5, the run now makes a Control run: the same pytest
  argv on the original code. If tests run there (pytest exit 0 or 1), the Mutant broke the run
  and is killed. If the Control run ends in any other way (exit 4 or 5 again, a timeout, an
  interrupted or crashed pytest), the argv is the suspect and the run still aborts with exit 2
  (ADR 0018 amendment). The abort message says that a Control run on the original code ran and
  how it ended: a Control run that timed out no longer reads as a bad `--pytest-args`.
  The Control run is not a Mutant: the `Executor:` line leaves it out of its counts, as the
  `Time:` line leaves it out of its timing. Before, three Mutants could show as four runs.
- An Executor now reports `errored` for a pytest that ended with no result (exit 2 or 3, any
  other exit code, a signal, a process that did not start). It reported `killed` before, so one
  such Control run could clear a bad argv and score every later exit 4 as killed. A Mutant that
  ends `errored` is still a kill, and the report is unchanged.
- A node id from another pytest rootdir now aborts the run, the same way on every run and
  every Executor. The plan checks the node ids of a Site before it dispatches that Site's
  Mutant. The serial loop plans one Site at a time, so Mutants of earlier Sites run first;
  a parallel run plans every Site before it provisions a Worker. In 0.3.0 the result
  depended on timing: the run aborted, or each Mutant timed out and was scored killed. The
  message names the node id and says to run mutate4py from the pytest rootdir.

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
