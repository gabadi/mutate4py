Feature: QA — parallel --max-workers execution is observable end-to-end through the CLI

  # TRACKING: F6 (parallel-workers) — docs/plan.md; docs/spec.md §9 (REOPENED);
  #           docs/adr/0013-max-workers-restored-as-real-flag.md;
  #           docs/adr/0015-parallel-workers-via-uv-clone-per-worker.md;
  #           docs/adr/0012-run-loop-serial-only-no-worker-token.md (amended).
  #
  # CONTRACT:
  #   End-to-end QA for F6. Operates ONLY through the user interface: the
  #   `mutate4py <file> --max-workers N <coverage-flag> [options]` command, its printed
  #   lines, the exit code, and on-disk state (the source, .mutate4py.bak, the LCOV
  #   fixture, the .mutate4py/workers/ tree, and any sentinel the fake pytest test
  #   writes). No project API — QA never imports mutate4py or calls the runner directly.
  #   The QA agent writes: a Python source fixture with several known mutation sites on
  #   covered lines (so >= 2 sites are selected and the parallel path engages); a
  #   hand-written LCOV fixture; and a FAKE pytest test (a test file QA controls,
  #   selected via --pytest-args, no shell involved) whose pass/fail/sleep/file-touch
  #   behavior QA scripts to force outcomes and to observe which working directory
  #   each run executes in.
  #   QA asserts on stdout (the "Mutation workers:" line, per-mutant "worker-<k>" tokens,
  #   the report), exit code, and disk (the worker tree's presence during vs after).
  #
  # CONSTRAINTS:
  #   - The fixture must have ENOUGH covered, selected sites (>= 2) that --max-workers >= 2
  #     takes the parallel path; QA reads the "Selected mutation sites:" header line to
  #     confirm the count before asserting parallel behavior.
  #   - QA controls the fake pytest test end to end (pass / fail / sleep past timeout),
  #     and can branch on whether the source copy currently holds a mutant, so
  #     the baseline passes while specific mutants are killed / survive / time out.
  #   - The "Mutation workers:" line and each per-mutant "worker-<k>" token are asserted
  #     from stdout; the parallel per-mutant line format is asserted byte-for-byte.
  #   - QA cannot assume per-mutant line ORDER on the parallel path (workers race); it
  #     asserts the SET of per-mutant lines (one per selected site, each with a token) and
  #     asserts the report tallies, which are deterministic.
  #   - To observe isolation, the fake pytest test records its own working directory
  #     (writes os.getcwd() to a per-run sentinel); QA confirms parallel runs execute
  #     under a .mutate4py/workers/.../worker-<k> path, not the original directory.
  #
  # SEQUENCING:
  #   - Each case: write source + LCOV + fake pytest test, run the CLI, assert on
  #     stdout/exit/disk, tear down the temp dir.
  #   - The worker-tree-cleanup case observes .mutate4py/workers/ DURING the run (via a
  #     fake pytest test that inspects the tree on first invocation) and AFTER the run
  #     (via a post-run directory check).
  #
  # NFR:
  #   - Assertions are on user-visible output and files only; no scraping of internal state.
  #   - The timeout/abort cases must finish quickly: short baseline, small timeout-factor.
  #   - The worker-failure case asserts BOTH non-zero exit AND the absence of a
  #     "Mutation Report" (no partial/misleading report leaks).
  #
  # SIDE EFFECTS:
  #   - QA writes only into its own temp dir. After a successful parallel run it asserts
  #     the original source is restored (no mutant spliced) with a fresh manifest footer,
  #     that no .mutate4py.bak remains, and that no .mutate4py/workers/ tree remains.
  #
  # SCOPE:
  #   - Does NOT: exercise --max-workers PARSING / validation (F5 QA owns that); QA always
  #     supplies an already-accepted value.
  #   - Does NOT: re-assert serial run-loop behavior (F4 QA owns it) beyond the parallel
  #     additions; QA supplies covered LCOV so sites are selected, then asserts parallelism.
  #   - ASSUMED: `uv` and the installed `mutate4py` entry point are on PATH; QA uses the
  #     same affordances a user would.
  #
  # UX INTENT: none
  # Design artifacts: none

  Background:
    Given a temp working directory the QA agent owns and tears down
    And a Python source fixture "calc.py" with covered mutation sites on lines "3,5,7,9"
    And a hand-written LCOV "cov.info" with SF matching "calc.py" and DA hits on lines "3,5,7,9"
    And a fake pytest test the QA agent scripts per outcome

  # parallel-workers_qa-1: QA sees the workers line track the flag across serial and parallel
  Scenario Outline: QA confirms the Mutation workers line prints whenever --max-workers is over zero
    Given the fake pytest test exits nonzero for every mutant while the baseline passes
    When the QA agent runs "mutate4py calc.py --lcov cov.info --max-workers <workers> --pytest-args tests --timeout-factor 2"
    Then stdout "<containsLine>" contain "Mutation workers:"
    And the exit status is zero

    Examples:
      | workers | containsLine |
      | 0       | does not     |
      | 1       | does         |
      | 4       | does         |

  # parallel-workers_qa-2: QA sees the worker token only on the parallel path
  Scenario Outline: QA confirms worker-<k> tokens appear only when the parallel engine runs
    Given the fake pytest test exits nonzero for every mutant while the baseline passes
    When the QA agent runs "mutate4py calc.py --lcov cov.info --max-workers <workers> --pytest-args tests --timeout-factor 2"
    Then every per-mutant line in stdout "<containsToken>" contain a "worker-" token

    Examples:
      | workers | containsToken |
      | 1       | does not      |
      | 4       | does          |

  # parallel-workers_qa-3: QA reads the clamped worker count off the workers line
  Scenario: QA sees --max-workers clamped to the selected-site count on the workers line
    Given the fake pytest test exits nonzero for every mutant while the baseline passes
    When the QA agent runs "mutate4py calc.py --lcov cov.info --max-workers 9 --pytest-args tests --timeout-factor 2"
    Then stdout contains "Selected mutation sites: 4"
    And stdout contains "Mutation workers: 4"

  # parallel-workers_qa-4: QA forces each classification on the parallel path
  Scenario Outline: QA drives killed / survived / timeout under --max-workers and sees the status
    Given the fake pytest test makes the mutated run "<outcome>" while the baseline passes
    When the QA agent runs "mutate4py calc.py --lcov cov.info --max-workers 4 --pytest-args tests --timeout-factor 2"
    Then stdout contains a per-mutant line matching "worker-<k> <status> line " for that mutant
    And the exit status is zero

    Examples:
      | outcome            | status   |
      | exit nonzero       | killed   |
      | exit zero          | survived |
      | sleep past timeout | timeout  |

  # parallel-workers_qa-5: QA confirms the report is deterministic regardless of worker timing
  Scenario: QA sees the same report tallies and survivor set across repeated parallel runs
    Given the fake pytest test makes "1" of the 4 mutants exit zero and the rest exit nonzero
    When the QA agent runs "mutate4py calc.py --lcov cov.info --max-workers 4 --pytest-args tests --timeout-factor 2" twice
    Then both runs print "Killed: 3"
    And both runs print "Survived: 1"
    And both runs list the same site under "Survivors:"

  # parallel-workers_qa-6: QA observes each parallel mutant runs in its own worker directory
  Scenario: QA confirms the test command runs under a per-worker copy, not the original dir
    Given the fake pytest test records its working directory to a sentinel and exits nonzero
    When the QA agent runs "mutate4py calc.py --lcov cov.info --max-workers 4 --pytest-args tests --timeout-factor 2"
    Then the recorded working directories are under ".mutate4py/workers/"
    And none of the recorded working directories is the original working directory

  # parallel-workers_qa-7: QA confirms the worker tree is created during and gone after the run
  Scenario: QA sees the worker tree present during the run and removed afterward
    Given the fake pytest test checks for a ".mutate4py/workers/" tree on its first call and exits nonzero
    When the QA agent runs "mutate4py calc.py --lcov cov.info --max-workers 4 --pytest-args tests --timeout-factor 2"
    Then the fake pytest test observed a ".mutate4py/workers/" tree during the run
    And no ".mutate4py/workers/" tree exists in the working directory after the run

  # parallel-workers_qa-8: QA confirms the original source is restored and re-stamped after a parallel run
  Scenario: QA confirms the original source is byte-restored with a fresh manifest after a parallel run
    Given the bytes of "calc.py" before any manifest footer are recorded
    And the fake pytest test exits nonzero for every mutant
    When the QA agent runs "mutate4py calc.py --lcov cov.info --max-workers 4 --pytest-args tests --timeout-factor 2"
    Then the body of "calc.py" above the manifest footer is unchanged
    And "calc.py" ends with a "mutate4py-manifest-begin" / "mutate4py-manifest-end" footer
    And no ".mutate4py.bak" file exists in the working directory

  # parallel-workers_qa-9: QA confirms a worker failure aborts with no report
  Scenario: QA sees a scripted worker failure abort the parallel run with no report
    Given the fake pytest test exits nonzero for every mutant while the baseline passes
    And one worker copy is made unwritable so its restore fails
    When the QA agent runs "mutate4py calc.py --lcov cov.info --max-workers 4 --pytest-args tests --timeout-factor 2"
    Then the exit status is non-zero
    And stdout does not contain "Mutation Report"
