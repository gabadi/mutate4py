Feature: QA — the coverage gate is observable end-to-end through --scan

  # TRACKING: F3 (coverage-gate) — docs/plan.md; docs/spec.md §6, §8 (--scan output);
  #           docs/adr/0007-coverage-default-path-and-line-only-gate.md;
  #           docs/adr/0008-coverage-flags-pairwise-exclusive.md;
  #           docs/adr/0009-coverage-partition-surfaces-via-scan.md
  #
  # CONTRACT:
  #   End-to-end QA for F3. Operates ONLY through the user interface: the
  #   `mutate4py <file> --scan <coverage-flag>` command, its printed lines, the
  #   exit code, and on-disk files. No project API — QA never imports mutate4py
  #   or calls the parser / gate directly.
  #   The QA agent writes Python source fixtures and hand-authored LCOV files to a
  #   temp directory it creates and tears down, runs the CLI, and asserts on:
  #   stdout (the "Total / Covered / Uncovered mutation sites:" lines), the exit
  #   code, the cov-cmd run-count sentinel, and the bytes of the source file.
  #
  # CONSTRAINTS:
  #   - QA controls every byte of each LCOV fixture (TN:, SF:<path>, DA:<line>,<count>,
  #     optional BRDA:, end_of_record) — a user could hand-write the same file.
  #   - A source fixture is a .py file with exactly one `a > b` style site per known
  #     line; QA confirms the site lines first with `mutate4py <file> --scan` (no
  #     coverage flag) and reads "Total mutation sites: <n>".
  #   - The covered + uncovered counts QA reads must sum to the Total line.
  #   - --cov-cmd's run-once guarantee is observed via a sentinel the command appends
  #     to on each invocation (e.g. one byte per run) — never by inspecting internals.
  #   - The default-path cases use exactly `coverage.lcov` in the working directory.
  #
  # SEQUENCING:
  #   - Each case: write fixtures, run the CLI, assert on stdout/exit/disk, tear down.
  #
  # NFR:
  #   - Assertions are on user-visible output and files only; no log scraping of
  #     internal state.
  #   - Usage-error cases assert BOTH a non-zero exit AND the absence of the
  #     Covered/Uncovered lines (a partial partition must never leak on error).
  #
  # SIDE EFFECTS:
  #   - QA writes only into its own temp dir. After a successful run it asserts the
  #     source fixture is byte-unchanged and no `.mutate4py.bak` was created.
  #
  # SCOPE:
  #   - Does NOT: assert killed/survived/timeout, run a mutant, or read a run report (F4).
  #   - Does NOT: assert manifest footer behavior (F2 QA owns that).
  #   - Does NOT: exercise the full flag matrix / mutual-exclusion beyond the three
  #     coverage flags' pairwise exclusivity (F5 QA owns the rest).
  #   - ASSUMED: the installed `mutate4py` entry point is on PATH (or invoked via the
  #     project's documented run command); QA uses the same affordance a user would.
  #
  # UX INTENT: none
  # Design artifacts: none

  Background:
    Given a temp working directory the QA agent owns and tears down
    And a Python source fixture "calc.py" with exactly one mutation site per line on "3,5,7"
    And the baseline "mutate4py calc.py --scan" reports "Total mutation sites: 3"

  # coverage_qa-1: line gate — covered vs uncovered through --scan
  Scenario Outline: QA sees covered/uncovered counts shift with the LCOV DA records
    Given a hand-written LCOV "cov.info" with SF matching "calc.py" and DA hits on lines "<covered>"
    When the QA agent runs "mutate4py calc.py --scan --lcov cov.info"
    Then stdout contains "Total mutation sites: 3"
    And stdout contains "Covered mutation sites: <coveredCount>"
    And stdout contains "Uncovered mutation sites: <uncoveredCount>"
    And the exit status is zero

    Examples:
      | covered | coveredCount | uncoveredCount |
      | 3,5,7   | 3            | 0              |
      | 3,7     | 2            | 1              |
      |         | 0            | 3              |

  # coverage_qa-2: a DA count of zero is uncovered
  Scenario: QA sees a zero-hit DA record counted as uncovered
    Given a hand-written LCOV "cov.info" with SF matching "calc.py" and the record "DA:5,0"
    When the QA agent runs "mutate4py calc.py --scan --lcov cov.info"
    Then stdout contains "Covered mutation sites: 0"
    And stdout contains "Uncovered mutation sites: 3"

  # coverage_qa-3: branch (BRDA) data alone never marks a line covered
  Scenario: QA sees branch-only LCOV data ignored by the gate
    Given a hand-written LCOV "cov.info" with SF matching "calc.py" containing only "BRDA:5,0,0,1" for line 5
    When the QA agent runs "mutate4py calc.py --scan --lcov cov.info"
    Then stdout contains "Covered mutation sites: 0"
    And stdout contains "Uncovered mutation sites: 3"

  # coverage_qa-4: suffix path matching — absolute fixture vs bare-basename SF
  Scenario Outline: QA confirms suffix matching across absolute-vs-relative SF paths
    Given a hand-written LCOV "cov.info" whose SF is "<sfPath>" with DA hits on line 5
    When the QA agent runs "mutate4py <abspath>/calc.py --scan --lcov cov.info"
    Then stdout contains "Covered mutation sites: <coveredCount>"

    Examples:
      | sfPath              | coveredCount |
      | calc.py             | 1            |
      | other/elsewhere.py  | 0            |

  # coverage_qa-5: --cov-cmd runs exactly once and drives the partition
  Scenario: QA proves --cov-cmd is invoked once via a run-count sentinel
    Given a coverage command that appends one byte to "cov-runs.log" and writes "cov.info" with DA hits on line 5
    When the QA agent runs "mutate4py calc.py --scan --cov-cmd '<that command>'"
    Then stdout contains "Covered mutation sites: 1"
    And the file "cov-runs.log" is exactly one byte
    And the exit status is zero

  # coverage_qa-6: --reuse-coverage reads the default path coverage.lcov
  Scenario: QA confirms --reuse-coverage reads coverage.lcov without regenerating
    Given a hand-written LCOV at the default path "coverage.lcov" with SF matching "calc.py" and DA hits on line 5
    When the QA agent runs "mutate4py calc.py --scan --reuse-coverage"
    Then stdout contains "Covered mutation sites: 1"
    And no coverage command was run

  # coverage_qa-7: a missing/unusable coverage source is a hard error with no counts
  Scenario Outline: QA confirms a missing coverage source exits non-zero and prints no counts
    Given there is no readable LCOV at "<missing>"
    When the QA agent runs "mutate4py calc.py --scan <flag>"
    Then the exit status is non-zero
    And stdout does not contain "Covered mutation sites:"
    And stdout does not contain "Uncovered mutation sites:"

    Examples:
      | flag                | missing       |
      | --reuse-coverage    | coverage.lcov |
      | --lcov missing.info | missing.info  |

  # coverage_qa-8: the three coverage flags are pairwise-exclusive
  Scenario Outline: QA confirms more than one coverage flag is a usage error
    Given each referenced file in "<flags>" exists so the failure is the exclusivity check
    When the QA agent runs "mutate4py calc.py --scan <flags>"
    Then the exit status is non-zero
    And stdout does not contain "Covered mutation sites:"

    Examples:
      | flags                            |
      | --lcov cov.info --reuse-coverage |
      | --cov-cmd CMD --lcov cov.info    |
      | --cov-cmd CMD --reuse-coverage   |

  # coverage_qa-9: coverage acquisition never mutates the source
  Scenario: QA confirms the source is byte-unchanged and no backup is left
    Given the bytes of "calc.py" are recorded before the run
    And a hand-written LCOV "cov.info" with SF matching "calc.py" and DA hits on lines "3,5,7"
    When the QA agent runs "mutate4py calc.py --scan --lcov cov.info"
    Then the bytes of "calc.py" are unchanged after the run
    And no ".mutate4py.bak" file exists in the working directory
