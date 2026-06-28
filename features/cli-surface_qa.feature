Feature: QA — the CLI surface is observable end-to-end through the command

  # TRACKING: F5 (cli-surface) — docs/plan.md; docs/spec.md §2, §8, §9;
  #           docs/adr/0013-max-workers-restored-as-real-flag.md;
  #           docs/adr/0014-cli-validation-mirrors-upstream-parse-model.md;
  #           docs/adr/0008-coverage-flags-pairwise-exclusive.md
  #
  # CONTRACT:
  #   End-to-end QA for F5. Operates ONLY through the user interface: the
  #   `mutate4py <file> [options]` command, its stdout/stderr, and its exit code.
  #   No project API — QA never imports mutate4py or calls the parser directly.
  #   The QA agent writes: a real Python source fixture with at least one mutation
  #   site, and (for accept cases that dispatch to the run loop) a minimal LCOV
  #   fixture + a fast fake --test-command, so an accepted invocation can complete
  #   cheaply. QA asserts on exit code (zero vs non-zero), and on the presence/absence
  #   of marker strings in the printed output.
  #
  # CONSTRAINTS:
  #   - QA distinguishes ACCEPT from REJECT by exit code: a usage error exits NON-ZERO
  #     and prints no run output; an accepted no-run mode (--scan/--update-manifest) or
  #     a completed run exits zero.
  #   - For accept cases QA always supplies an otherwise-valid invocation (a real file,
  #     and a coverage flag + fake test command when the run loop is reached) so the only
  #     variable under test is the flag/combination being validated.
  #   - QA asserts a usage error does NO work: for a reject case it confirms the source
  #     file is byte-identical afterwards (no manifest re-embedded, no mutant spliced) and
  #     no .mutate4py.bak appears — proving validation fired before any dispatch.
  #   - --help is asserted to exit zero, print the usage summary, and that the summary
  #     text contains "--max-workers".
  #   - QA controls the fake --test-command end to end (a small script it writes), the
  #     same affordance a real user has; it does not scrape internal state.
  #
  # SEQUENCING:
  #   - Each case: write the source fixture (and LCOV + fake test command when the
  #     invocation should reach the run loop), run the CLI once, assert exit code +
  #     output markers + on-disk effects, tear down the temp dir.
  #   - The --help case is run with deliberately-invalid companion args to prove --help
  #     wins before validation (exit zero despite the bad combo).
  #
  # NFR:
  #   - Assertions are on exit code, printed output, and files only.
  #   - Reject cases must be cheap: they exit before any test run, so no fake command is
  #     even needed for a pure usage-error assertion.
  #
  # SIDE EFFECTS:
  #   - QA writes only into its own temp dir. For a reject case it asserts the source
  #     fixture is unchanged and no .mutate4py.bak was created.
  #
  # SCOPE:
  #   - Does NOT: assert the run report body (F4 QA), the --scan count lines (F1/F3 QA),
  #     or the --update-manifest footer (F2 QA) — F5 QA asserts only that an accepted
  #     mode is REACHED (exit zero / its lead marker) and a rejected one is BLOCKED.
  #   - Does NOT: exercise actual parallel execution (F6 QA) — F5 QA confirms
  #     --max-workers is accepted/validated, not that workers run.
  #   - ASSUMED: the installed `mutate4py` entry point is on PATH (or invoked via the
  #     project's documented run command), the same affordance a user would use.
  #
  # UX INTENT: none
  # Design artifacts: none

  Background:
    Given a temp project directory with a real Python source file holding a mutation site

  # cli-surface-qa-1: a usage error exits non-zero and does no work
  Scenario Outline: a rejected invocation exits non-zero and leaves the source untouched
    When I invoke the mutate4py command described by "<invocation>"
    Then the command exits non-zero
    And the printed output names the offending flag or combination
    And the source file is byte-identical to before the run
    And no ".mutate4py.bak" file was created

    Examples:
      | invocation                                  |
      | --mutation-warning 0                        |
      | --max-workers -1                            |
      | --timeout-factor 1.5                        |
      | --lines 7,x                                 |
      | --scan --max-workers 4                      |
      | --scan --mutate-all                         |
      | --update-manifest --lines 7                 |
      | --since-last-run --mutate-all               |
      | --lcov cov.info --reuse-coverage            |
      | --bogus-flag                                |
      | (a path that does not exist)                |
      | (no source file argument)                   |
      | --max-workers (with no value)               |

  # cli-surface-qa-2: --help exits zero, prints usage, and lists --max-workers
  Scenario: --help prints the usage summary and wins over invalid companion args
    When I invoke "mutate4py --help --scan --mutate-all"
    Then the command exits zero
    And the printed output contains a usage summary
    And the printed output contains "--max-workers"

  # cli-surface-qa-3: an accepted no-run mode reaches its mode and exits zero
  Scenario Outline: an accepted no-run mode is reached
    When I invoke the mutate4py command with the accepted "<mode>"
    Then the command exits zero
    And the printed output contains the mode's lead marker "<marker>"

    Examples:
      | mode              | marker            |
      | --scan            | Mutation scan:    |
      | --update-manifest | manifest          |

  # cli-surface-qa-4: an accepted run-loop invocation with --max-workers is accepted and completes
  Scenario: --max-workers alongside a coverage flag is accepted and runs
    Given a minimal LCOV fixture covering the site and a fast fake test command
    When I invoke "mutate4py <file> --lcov cov.info --max-workers 4 --test-command <fake>"
    Then the command exits zero
    And the printed output contains "Mutation run:"

  # cli-surface-qa-5: --max-workers combines with a selection flag without error
  Scenario: --max-workers and a selection flag are accepted together
    Given a minimal LCOV fixture covering the site and a fast fake test command
    When I invoke "mutate4py <file> --lcov cov.info --max-workers 4 --mutate-all --test-command <fake>"
    Then the command exits zero
