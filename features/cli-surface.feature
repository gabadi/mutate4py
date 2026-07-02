# mutation-stamp: sha256=4bb2047f6fd9b297f4f198a164f7df2fd26e72d9f9ba18789bbe56d7ed007d09
# acceptance-mutation-manifest-begin
# {"version":1,"tested_at":"2026-07-02T14:16:58.492908Z","feature_name":"The CLI surface parses, validates, and dispatches the flag matrix","feature_path":"/Users/gabadi/workspace/addi/mutate4py/features/cli-surface.feature","background_hash":"1203275c6eabf9fc410f98f69ac6af108b327191aeca7b251b7f196f4d6e6eaf","implementation_hash":"unknown","scenarios":[{"index":0,"name":"the full flag matrix parses and applies its default","scenario_hash":"f58044050f009b80096d5ade66cdc5d6048e4029c5c683144d237429011492bc","mutation_count":24,"result":{"Total":24,"Killed":24,"Survived":0,"Errors":0},"tested_at":"2026-07-02T02:54:24.264819Z"},{"index":1,"name":"a numeric flag rejects values that are not positive integers","scenario_hash":"6f1c256c9442246f7a2d6d6bf02c61aff355b799164b881eecfa1599978288c0","mutation_count":11,"result":{"Total":11,"Killed":11,"Survived":0,"Errors":0},"tested_at":"2026-07-02T02:54:24.264819Z"},{"index":2,"name":"a value flag with a missing value is rejected","scenario_hash":"2eeab52799ce2b3e6662c4bba4851a503dc9c168109362e87ebb23a6f5309e2f","mutation_count":5,"result":{"Total":5,"Killed":5,"Survived":0,"Errors":0},"tested_at":"2026-07-02T02:54:24.264819Z"},{"index":3,"name":"a no-run mode rejects being combined with an execution option","scenario_hash":"c547fbec1018baff4e0a5b38c8405f20d50e9917ebb4ee6202dcad0ea3de4ed0","mutation_count":24,"result":{"Total":24,"Killed":24,"Survived":0,"Errors":0},"tested_at":"2026-07-02T02:54:24.264819Z"},{"index":4,"name":"combining two selection flags is a usage error","scenario_hash":"d2954272964e2887ddc585f79ecee9abf28d1b46ce94ac3b774c3494d59c2f72","mutation_count":6,"result":{"Total":6,"Killed":6,"Survived":0,"Errors":0},"tested_at":"2026-07-02T02:54:24.264819Z"},{"index":5,"name":"--max-workers is accepted alongside a selection flag","scenario_hash":"65f8dd172a38a062d2ba6c54c8c0a253173e7732ea67de7c08c5674e7cd840b4","mutation_count":3,"result":{"Total":3,"Killed":3,"Survived":0,"Errors":0},"tested_at":"2026-07-02T02:54:24.264819Z"},{"index":6,"name":"an unknown flag or missing source file is rejected","scenario_hash":"813c2a7317dad0bca22919363855242b2948b289ef215390fe7d6fd47afcc940","mutation_count":3,"result":{"Total":3,"Killed":3,"Survived":0,"Errors":0},"tested_at":"2026-07-02T02:54:24.264819Z"},{"index":7,"name":"--help short-circuits to usage even with invalid args","scenario_hash":"aeb3ab3b6fafbd8eadfa31d3c68818374fd4288c2d9b1bf9459654db45b577d4","mutation_count":3,"result":{"Total":3,"Killed":3,"Survived":0,"Errors":0},"tested_at":"2026-07-02T02:54:24.264819Z"},{"index":8,"name":"validated options are routed to the right behaviour","scenario_hash":"ed881adfbdea0ad219b14c17fbc9e4126192d00e628d71e3ec4805536181a6dd","mutation_count":6,"result":{"Total":6,"Killed":6,"Survived":0,"Errors":0},"tested_at":"2026-07-02T02:54:24.264819Z"}]}
# acceptance-mutation-manifest-end

Feature: The CLI surface parses, validates, and dispatches the flag matrix

  # TRACKING: F5 (cli-surface) — docs/plan.md; docs/spec.md §2 (CLI surface),
  #           §8 (--scan / --update-manifest output strings), §9 (parallelism, reopened);
  #           docs/adr/0013-max-workers-restored-as-real-flag.md;
  #           docs/adr/0014-cli-validation-mirrors-upstream-parse-model.md;
  #           docs/adr/0015-parallel-workers-via-uv-clone-per-worker.md;
  #           docs/adr/0008-coverage-flags-pairwise-exclusive.md
  #           Upstream ground truth: unclebob/mutate4go internal/cli/cli.go
  #           (ValidateArgs, consumeValueOption, parsePositiveInt, parseLines).
  #
  # CONTRACT:
  #   command: mutate4py <file> [options]   (one file per invocation)
  #   request — the §2 flag matrix F5 parses and validates:
  #     <file>               — positional, required; the source to mutate.
  #     --scan               — no-run mode: count sites (F1 surface).
  #     --update-manifest    — no-run mode: rewrite the footer manifest (F2 surface).
  #     --lines L1,L2,...     — selection: comma-separated POSITIVE ints.
  #     --since-last-run      — selection: only changed functions.
  #     --mutate-all          — selection: all covered sites despite manifest.
  #     --mutation-warning N  — positive int, default 50.
  #     --timeout-factor N    — positive int, default 10.
  #     --test-command CMD    — string, default "pytest" ([PY] §2).
  #     --max-workers N       — positive int, default 0/unset = serial (ADR 0013).
  #     --cov-cmd CMD | --lcov PATH | --reuse-coverage — the three coverage flags.
  #     --verbose             — log to stderr.
  #     --help                — print usage, exit 0.
  #   on ACCEPT: parsed options are dispatched —
  #     --scan -> F1 scan surface; --update-manifest -> F2 manifest write;
  #     otherwise -> the F4 run loop (serial, or the F6 worker engine when
  #     --max-workers >= 2 AND sites >= 2). F5 routes; it never re-implements a target.
  #   on REJECT (usage error): a usage/error message is printed and the process exits
  #     NON-ZERO, having run NO analysis and NO test command. Reject classes:
  #     unknown flag, missing value for a value flag, invalid numeric value,
  #     illegal flag combination, missing/nonexistent source file.
  #
  # CONSTRAINTS:
  #   - Positive-int flags (--mutation-warning, --timeout-factor, --max-workers) require
  #     an integer >= 1; non-integer or <= 0 is a usage error (parsePositiveInt).
  #   - --lines requires a comma-separated list of POSITIVE integers (parseLines).
  #   - Mutual exclusion (fail-loud, never silent-precedence; ADR 0008, 0014):
  #       * --scan and --update-manifest: exclusive of each other AND of every execution
  #         option (--lines, --since-last-run, --mutate-all, non-default --timeout-factor,
  #         non-default --test-command, --max-workers).
  #       * --since-last-run / --mutate-all / --lines: PAIRWISE exclusive.
  #       * --cov-cmd / --lcov / --reuse-coverage: PAIRWISE exclusive (F3 ADR 0008).
  #   - --max-workers joins ONLY the scan/update-manifest exclusion; it MAY combine with
  #     the selection flags (it does not conflict with --lines/--since-last-run/--mutate-all).
  #   - Missing source file (no positional, or path does not exist) is a usage error.
  #   - Defaults when unset: --mutation-warning 50, --timeout-factor 10,
  #     --test-command "pytest", --max-workers serial.
  #
  # SEQUENCING:
  #   - --help is honoured BEFORE any validation: it prints usage and exits 0 even
  #     alongside otherwise-invalid args (cli.go:63-71).
  #   - Validation completes BEFORE any dispatch: a rejected invocation does no
  #     analysis and runs no test command (no partial work on a usage error).
  #
  # NFR:
  #   - Usage errors are fail-loud: non-zero exit so CI/scripts can branch on it; the
  #     message names the offending flag/combination, not a generic failure.
  #   - A rejected combination never silently drops a flag the user passed (the
  #     fail-loud contract that the hard errors exist to enforce).
  #
  # SIDE EFFECTS:
  #   - F5 adds no new output strings: --scan / --update-manifest text is F1/F2's
  #     (§8), the run report is F4's. F5 only parses, validates, and routes.
  #   - --help's usage summary must LIST --max-workers (restored, ADR 0013).
  #   - The accepted --max-workers count is passed through to the run dispatcher for
  #     F6 to act on; F5 itself does not execute workers.
  #
  # SCOPE:
  #   - Does NOT: execute parallel workers (F6) — F5 validates --max-workers and passes
  #     the count through; the serial/parallel switch and worker engine are F6.
  #   - Does NOT: re-implement --scan counting (F1), --update-manifest writing (F2), the
  #     LCOV gate (F3), or the run loop (F4) — it dispatches to them.
  #   - Does NOT: re-create the §8 --scan / --update-manifest output strings (F1/F2 own
  #     them); F5 only routes to the mode that prints them.
  #   - ASSUMED: the exact arg-parser (argparse vs hand-rolled) and the exact non-zero
  #     exit code (1 vs 2) are the coder's to pin; this feature fixes the usage-error
  #     OUTCOME (message text parameterized, non-zero exit) not the mechanism/code.
  #
  # UX INTENT: none
  # Design artifacts: none

  Background:
    Given an existing Python source file with discovered mutation sites

  # cli-surface-1: every §2 flag parses to its option with the documented default
  Scenario Outline: the full flag matrix parses and applies its default
    When I run mutate4py with the flag "<flag>"
    Then the option "<option>" is set to "<value>"
    And the invocation is accepted

    Examples:
      | flag                  | option           | value     |
      | --mutation-warning 25 | mutation-warning | 25        |
      | --timeout-factor 4    | timeout-factor   | 4         |
      | --test-command "tox"  | test-command     | tox       |
      | --max-workers 4       | max-workers      | 4         |
      | (none)                | mutation-warning | 50        |
      | (none)                | timeout-factor   | 10        |
      | (none)                | test-command     | pytest    |
      | (none)                | max-workers      | serial    |

  # cli-surface-2: positive-int flags reject non-integer and non-positive values
  Scenario Outline: a numeric flag rejects values that are not positive integers
    When I run mutate4py with the flag "<flag>"
    Then the invocation is a usage error
    And the command exits with a non-zero status
    And no analysis or test run occurs

    Examples:
      | flag                   |
      | --mutation-warning 0   |
      | --mutation-warning -3  |
      | --mutation-warning two |
      | --timeout-factor 0     |
      | --timeout-factor 1.5   |
      | --max-workers 0        |
      | --max-workers -1       |
      | --max-workers many     |
      | --lines 0              |
      | --lines 7,-2           |
      | --lines 7,x            |

  # cli-surface-3: a value flag given no value is a usage error
  Scenario Outline: a value flag with a missing value is rejected
    When I run mutate4py with a trailing "<flag>" and no value
    Then the invocation is a usage error
    And the command exits with a non-zero status

    Examples:
      | flag             |
      | --mutation-warning |
      | --timeout-factor   |
      | --test-command     |
      | --max-workers      |
      | --lines            |

  # cli-surface-4: --scan and --update-manifest reject every execution option
  Scenario Outline: a no-run mode rejects being combined with an execution option
    When I run mutate4py with "<mode>" and "<other>"
    Then the invocation is a usage error
    And the command exits with a non-zero status

    Examples:
      | mode              | other             |
      | --scan            | --update-manifest |
      | --scan            | --lines 7         |
      | --scan            | --since-last-run  |
      | --scan            | --mutate-all      |
      | --scan            | --timeout-factor 5 |
      | --scan            | --test-command "tox" |
      | --scan            | --max-workers 4   |
      | --update-manifest | --scan            |
      | --update-manifest | --lines 7         |
      | --update-manifest | --since-last-run  |
      | --update-manifest | --mutate-all      |
      | --update-manifest | --max-workers 4   |

  # cli-surface-5: the three selection flags are pairwise exclusive
  Scenario Outline: combining two selection flags is a usage error
    When I run mutate4py with "<one>" and "<two>"
    Then the invocation is a usage error
    And the command exits with a non-zero status

    Examples:
      | one              | two          |
      | --since-last-run | --mutate-all |
      | --since-last-run | --lines 7    |
      | --mutate-all     | --lines 7    |

  # cli-surface-6: --max-workers may combine with selection flags (it is not exclusive of them)
  Scenario Outline: --max-workers is accepted alongside a selection flag
    When I run mutate4py with "--max-workers 4" and "<selection>"
    Then the invocation is accepted

    Examples:
      | selection        |
      | --lines 7        |
      | --since-last-run |
      | --mutate-all     |

  # cli-surface-7: an unknown flag or a missing source file is a usage error
  Scenario Outline: an unknown flag or missing source file is rejected
    When I run mutate4py described by "<invocation>"
    Then the invocation is a usage error
    And the command exits with a non-zero status

    Examples:
      | invocation                        |
      | a valid file with --bogus-flag    |
      | no positional source file         |
      | a source path that does not exist |

  # cli-surface-8: --help prints usage and exits 0, ahead of any validation
  Scenario Outline: --help short-circuits to usage even with invalid args
    When I run mutate4py with "--help" and "<alongside>"
    Then the usage summary is printed
    And the usage summary lists "--max-workers"
    And the command exits with status zero

    Examples:
      | alongside        |
      | (nothing)        |
      | --max-workers 0  |
      | --scan --mutate-all |

  # cli-surface-9: an accepted invocation dispatches to the matching mode
  Scenario Outline: validated options are routed to the right behaviour
    When I run mutate4py with the accepted flags "<flags>"
    Then the run is dispatched to the "<target>" behaviour

    Examples:
      | flags             | target          |
      | --scan            | scan surface    |
      | --update-manifest | manifest write  |
      | (a coverage flag) | run loop        |

  # cli-surface-10: the accepted --max-workers count is passed through to the dispatcher
  Scenario: an accepted --max-workers count reaches the run dispatcher
    When I run mutate4py with the accepted flags "--max-workers 4 (a coverage flag)"
    Then the run is dispatched to the "run loop" behaviour
    And the dispatcher receives a worker count of "4"
