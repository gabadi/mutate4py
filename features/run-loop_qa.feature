Feature: QA — the mutation run loop is observable end-to-end through the CLI

  # TRACKING: F4 (run-loop) — docs/plan.md; docs/spec.md §7, §8, §9;
  #           docs/adr/0010-run-loop-composes-f3-coverage-and-baseline-gate.md;
  #           docs/adr/0011-timeout-printed-verbatim-folded-into-killed.md;
  #           docs/adr/0012-run-loop-serial-only-no-worker-token.md
  #
  # CONTRACT:
  #   End-to-end QA for F4. Operates ONLY through the user interface: the
  #   `mutate4py <file> <coverage-flag> [options]` command, its printed lines, the
  #   exit code, and on-disk files (the source, .mutate4py.bak, the LCOV fixture,
  #   and any sentinel the fake test command writes). No project API — QA never
  #   imports mutate4py or calls the runner / classifier directly.
  #   The QA agent writes: a Python source fixture with known mutation sites; a
  #   hand-written LCOV fixture marking those lines covered; and a FAKE test command
  #   (a small script QA controls) whose exit code and sleep are scripted so QA can
  #   force killed / survived / timeout / baseline-fail outcomes deterministically.
  #   QA asserts on stdout (header, per-mutant lines, report), exit code, and disk.
  #
  # CONSTRAINTS:
  #   - QA controls the fake --test-command end to end: it can make the run exit zero
  #     (survived), non-zero (killed), or sleep past the timeout (timeout), and can
  #     branch its behavior on whether the source currently holds a mutant (so the
  #     baseline passes while a specific mutant is killed/survives) — all observable to
  #     a user who writes the same script.
  #   - Coverage is a hand-written LCOV fixture (SF matching the source, DA hits on the
  #     site lines) supplied via --lcov, or placed at coverage.lcov for --reuse-coverage.
  #   - QA reads counts and the Selected line from the header to know how many per-mutant
  #     lines to expect; the per-mutant line format is asserted byte-for-byte.
  #   - The Killed report total must equal killed + timeout outcomes QA scripted.
  #   - timeout outcomes are driven by a fake command that sleeps longer than
  #     timeout-factor × baseline; QA keeps the baseline fast and the factor small so the
  #     timeout window is short enough to test cheaply.
  #
  # SEQUENCING:
  #   - Each case: write source + LCOV + fake test command, run the CLI, assert on
  #     stdout/exit/disk, tear down the temp dir.
  #
  # NFR:
  #   - Assertions are on user-visible output and files only; no scraping of internal state.
  #   - The baseline-failure case asserts BOTH non-zero exit AND the absence of a
  #     "Mutation Report" and of a .mutate4py.bak (no partial run leaks).
  #   - The timeout case must finish quickly: short baseline, small timeout-factor.
  #
  # SIDE EFFECTS:
  #   - QA writes only into its own temp dir. After a successful run it asserts the
  #     source is restored (no mutant spliced) and carries a fresh manifest footer, and
  #     that no .mutate4py.bak remains.
  #
  # SCOPE:
  #   - Does NOT: assert --scan or --update-manifest output (F1/F2 QA own those).
  #   - Does NOT: exercise CLI flag validation / mutual-exclusion / --max-workers usage
  #     error (F5 QA owns those); QA always supplies a valid, already-accepted flag set.
  #   - Does NOT: assert the internal coverage gate (F3 QA owns it); QA supplies covered
  #     LCOV so sites are selected, then asserts run behavior.
  #   - ASSUMED: the installed `mutate4py` entry point is on PATH (or invoked via the
  #     project's documented run command); QA uses the same affordance a user would.
  #
  # UX INTENT: none
  # Design artifacts: none

  Background:
    Given a temp working directory the QA agent owns and tears down
    And a Python source fixture "calc.py" with covered mutation sites on lines "3,7"
    And a hand-written LCOV "cov.info" with SF matching "calc.py" and DA hits on lines "3,7"
    And a fake test command "runtests.sh" the QA agent scripts per outcome

  # run-loop_qa-1: QA forces each classification and reads it off the per-mutant line
  Scenario Outline: QA drives killed / survived / timeout and sees the status verbatim
    Given "runtests.sh" makes the mutated run "<outcome>" while the baseline passes
    When the QA agent runs "mutate4py calc.py --lcov cov.info --test-command ./runtests.sh --timeout-factor 2"
    Then stdout contains a line matching "[<n>/<total>] <status> line " for that mutant
    And the exit status is zero

    Examples:
      | outcome           | status   |
      | exit nonzero      | killed   |
      | exit zero         | survived |
      | sleep past timeout | timeout |

  # run-loop_qa-2: QA confirms timeout folds into Killed in the report
  Scenario: QA sees a timed-out mutant counted as Killed, not as a Timeout line
    Given "runtests.sh" makes one mutant sleep past the timeout and the rest exit nonzero
    When the QA agent runs "mutate4py calc.py --lcov cov.info --test-command ./runtests.sh --timeout-factor 2"
    Then stdout contains "timeout line "
    And stdout contains "Killed: 2"
    And stdout does not contain "Timeout:"

  # run-loop_qa-3: QA sees the Survivors block only when a mutant survives
  Scenario Outline: QA confirms the Survivors block is conditional on survived > 0
    Given "runtests.sh" makes "<survivedCount>" of the 2 mutants exit zero and the rest exit nonzero
    When the QA agent runs "mutate4py calc.py --lcov cov.info --test-command ./runtests.sh --timeout-factor 2"
    Then stdout contains "Survived: <survivedCount>"
    And stdout "<containsSurvivors>" contain "Survivors:"

    Examples:
      | survivedCount | containsSurvivors |
      | 0             | does not          |
      | 1             | does              |

  # run-loop_qa-4: QA confirms a failing baseline aborts before any mutant
  Scenario: QA sees a failing baseline abort the run with no report and no backup
    Given "runtests.sh" exits nonzero on the unmutated baseline run
    When the QA agent runs "mutate4py calc.py --lcov cov.info --test-command ./runtests.sh"
    Then the exit status is non-zero
    And stdout contains "baseline failed:"
    And stdout does not contain "Mutation Report"
    And no ".mutate4py.bak" file exists in the working directory

  # run-loop_qa-5: QA confirms the header has the count lines and no workers line
  Scenario: QA confirms the run header lines are present and no workers line appears
    Given "runtests.sh" exits nonzero for every mutant
    When the QA agent runs "mutate4py calc.py --lcov cov.info --test-command ./runtests.sh --timeout-factor 2"
    Then stdout contains "Mutation run: calc.py"
    And stdout contains "Total mutation sites:"
    And stdout contains "Selected mutation sites:"
    And stdout does not contain "Mutation workers:"
    And stdout does not contain "worker-"

  # run-loop_qa-6: QA confirms the source is restored and re-stamped after a run
  Scenario: QA confirms the source is byte-restored with a fresh manifest after the run
    Given the bytes of "calc.py" before any manifest footer are recorded
    And "runtests.sh" exits nonzero for every mutant
    When the QA agent runs "mutate4py calc.py --lcov cov.info --test-command ./runtests.sh --timeout-factor 2"
    Then the body of "calc.py" above the manifest footer is unchanged
    And "calc.py" ends with a "mutate4py-manifest-begin" / "mutate4py-manifest-end" footer
    And no ".mutate4py.bak" file exists in the working directory

  # run-loop_qa-7: QA confirms an interrupted run self-heals from the backup
  Scenario: QA confirms a leftover backup is restored and announced on the next run
    Given a ".mutate4py.bak" file holding a known prior source body exists in the working directory
    And "calc.py" on disk currently holds a leftover spliced mutant
    And "runtests.sh" exits nonzero for every mutant
    When the QA agent runs "mutate4py calc.py --lcov cov.info --test-command ./runtests.sh --timeout-factor 2"
    Then stdout contains "Restored source from backup (previous run was interrupted)."
    And the body of "calc.py" above the manifest footer matches the prior source body

  # run-loop_qa-8: QA confirms --reuse-coverage announces stale coverage before the header
  Scenario: QA sees the stale-coverage warning printed before the run header
    Given a hand-written LCOV at the default path "coverage.lcov" with DA hits on lines "3,7"
    And "runtests.sh" exits nonzero for every mutant
    When the QA agent runs "mutate4py calc.py --reuse-coverage --test-command ./runtests.sh --timeout-factor 2"
    Then stdout contains "Reusing existing coverage; covered/uncovered classification may be stale."
    And that line appears before "Mutation run: calc.py" in stdout
