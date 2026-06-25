Feature: QA — site discovery is observable end-to-end through the mutate4py CLI

  # TRACKING: F1 (site-discovery) — docs/plan.md; docs/spec.md §8 (--scan);
  #           docs/adr/0002-scan-counts-only-no-manifest-in-f1.md
  #
  # CONTRACT:
  #   End-to-end QA for F1. Operates ONLY through the user interface: the
  #   `mutate4py <file> --scan` command and its printed block. No project API.
  #   The QA agent runs the command against committed fixtures and asserts on the
  #   printed count lines, the warning line, exit codes, and that the file is
  #   unchanged on disk.
  #
  # CONSTRAINTS:
  #   - Verification uses committed Python fixtures. Each fixture's header comment
  #     states its expected Total mutation sites.
  #   - The QA agent asserts on printed lines only; it does not import mutate4py or
  #     inspect internal site lists.
  #   - No coverage file is supplied: --scan must work without one (it never reads
  #     coverage).
  #   - QA does not assert per-operator identity (that is a unit-test concern); it
  #     asserts the observable totals and the read-only contract.
  #
  # SEQUENCING: none
  #
  # NFR:
  #   - Re-running --scan on the same fixture prints an identical block.
  #
  # SIDE EFFECTS: none
  #   # --scan must not modify the fixture on disk.
  #
  # SCOPE:
  #   - Does NOT: assert coverage, killed/survived, or run-report output (F4).
  #   - Does NOT: assert manifest behaviour (F2) — fixtures carry no manifest, so
  #     "Manifest exists: false" and "Changed == Total" are the only manifest-related
  #     observations.
  #   - ASSUMED: `mutate4py <file> --scan` is the user-facing invocation and prints
  #     the §8 scan block to stdout.
  #
  # UX INTENT: none
  # Design artifacts: none

  Background:
    Given the mutate4py command-line tool is installed
    And a committed Python fixture whose header states its expected total sites

  # qa-site-discovery-1: the scan block reports the fixture's expected total
  Scenario Outline: scanning a fixture reports its expected total sites
    Given a fixture "<fixture>" with expected total <total>
    When the command "mutate4py <fixture> --scan" is run
    Then the command exits successfully
    And the output line "Mutation scan: <fixture>" is printed
    And the output line "Total mutation sites: <total>" is printed

    Examples:
      | fixture            | total |
      | mixed_operators.py | 6     |
      | module_level.py    | 2     |
      | empty_units.py     | 0     |

  # qa-site-discovery-2: with no manifest, Changed equals Total and Manifest exists is false
  Scenario: a fixture with no manifest reports changed equal to total
    Given a fixture "mixed_operators.py" with expected total 6
    When the command "mutate4py mixed_operators.py --scan" is run
    Then the output line "Changed mutation sites: 6" is printed
    And the output line "Manifest exists: false" is printed

  # qa-site-discovery-3: --scan is read-only and runs no tests
  Scenario: scanning leaves the fixture unchanged and runs no tests
    Given a fixture "mixed_operators.py"
    And a recorded copy of its contents
    When the command "mixed_operators.py --scan" is run through mutate4py
    Then the fixture contents on disk match the recorded copy exactly
    And no test command was executed

  # qa-site-discovery-4: the warning line appears only over the threshold
  Scenario Outline: the warning line is shown only when the total exceeds the threshold
    Given a fixture "<fixture>" with expected total <total>
    When the command "mutate4py <fixture> --scan --mutation-warning <threshold>" is run
    Then the warning line shown is "<warning>"

    Examples:
      | fixture            | total | threshold | warning                                          |
      | mixed_operators.py | 6     | 6         |                                                  |
      | mixed_operators.py | 6     | 5         | Warning: 6 mutation sites exceeds threshold 5.   |

  # qa-site-discovery-5: a missing file is a usage error with no scan block
  Scenario: scanning a path that does not exist fails as a usage error
    Given no file exists at "does_not_exist.py"
    When the command "mutate4py does_not_exist.py --scan" is run
    Then the command exits with a non-zero status
    And no "Mutation scan:" line is printed

  # qa-site-discovery-6: re-running is deterministic
  Scenario: two consecutive scans of the same fixture print identical blocks
    Given a fixture "mixed_operators.py"
    When the command "mutate4py mixed_operators.py --scan" is run twice
    Then both runs print the same scan block
