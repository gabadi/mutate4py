# mutation-stamp: sha256=bdfc4cb6dd3a1bbab17390cc025829b7af3dc62f8b146c7fae0ab851dbed7320
# acceptance-mutation-manifest-begin
# {"version":1,"tested_at":"2026-08-05T06:34:34Z","feature_name":"The CLI surface parses, validates, and dispatches the flag matrix","feature_path":"features/cli-surface.feature","background_hash":"1203275c6eabf9fc410f98f69ac6af108b327191aeca7b251b7f196f4d6e6eaf","implementation_hash":"sha256:270c59e799909ae28b518b18fdd82d84caf82d2b5e15ffabe26f611d1ebf7c63","scenarios":[{"index":0,"name":"the full flag matrix parses and applies its default","scenario_hash":"35e28bf7facb9d3c7fdfcac3937137c41d4622ce540cca20291f1fb3b14263d9","mutation_count":24,"result":{"Total":24,"Killed":24,"Survived":0,"Errors":0},"tested_at":"2026-08-05T06:34:34Z"},{"index":1,"name":"a numeric flag rejects values that are not positive integers","scenario_hash":"a2c7162b81dcdd3a79f489b3256f997b25d42a9660d3d68e859394d9502ef2ef","mutation_count":11,"result":{"Total":11,"Killed":11,"Survived":0,"Errors":0},"tested_at":"2026-08-05T06:34:34Z"},{"index":2,"name":"a value flag with a missing value is rejected","scenario_hash":"c37764cca4646af139a58f03693bab5820d727a41c92787bfc07beebdffb5b0a","mutation_count":5,"result":{"Total":5,"Killed":5,"Survived":0,"Errors":0},"tested_at":"2026-08-05T06:34:34Z"},{"index":3,"name":"a no-run mode rejects being combined with an execution option","scenario_hash":"30f46756fb76de41193baa294affbb621e661f5a1d670c3b26d7b4fae770d3fb","mutation_count":24,"result":{"Total":24,"Killed":24,"Survived":0,"Errors":0},"tested_at":"2026-08-05T06:34:34Z"},{"index":4,"name":"combining two selection flags is a usage error","scenario_hash":"88ff433e01244df649696d2076a6a8a2df4ee1a22f323d8c51400cb49ac80335","mutation_count":6,"result":{"Total":6,"Killed":6,"Survived":0,"Errors":0},"tested_at":"2026-08-05T06:34:34Z"},{"index":5,"name":"--max-workers is accepted alongside a selection flag","scenario_hash":"3ab1c84ab1c02366f62e18afb506789995ccc145af73681ae21b8cf9fff416f1","mutation_count":3,"result":{"Total":3,"Killed":3,"Survived":0,"Errors":0},"tested_at":"2026-08-05T06:34:34Z"},{"index":6,"name":"an unknown flag or missing source file is rejected","scenario_hash":"43c42d8a2bec629c31a639050708aa4aaae4036452dbceea3f40bd98a12868fd","mutation_count":3,"result":{"Total":3,"Killed":3,"Survived":0,"Errors":0},"tested_at":"2026-08-05T06:34:34Z"},{"index":7,"name":"--help short-circuits to usage even with invalid args","scenario_hash":"0f1c3f6768d7f821b590a1d9f8f3b9e9876f4f5dd78ef8813db0d5c33da45a2c","mutation_count":3,"result":{"Total":3,"Killed":3,"Survived":0,"Errors":0},"tested_at":"2026-08-05T06:34:34Z"},{"index":8,"name":"validated options are routed to the right behaviour","scenario_hash":"2053e21dff52520290af1b4bcd55de386ea5b0ad7ba405b96dcf62a575f6e11b","mutation_count":6,"result":{"Total":6,"Killed":6,"Survived":0,"Errors":0},"tested_at":"2026-08-05T06:34:34Z"}]}
# acceptance-mutation-manifest-end

Feature: The CLI surface parses, validates, and dispatches the flag matrix

  # TRACKING: F5 (cli-surface) — docs/adr/0015-parallel-workers-via-uv-clone-per-worker.md;
  #           docs/adr/0008-coverage-flags-pairwise-exclusive.md
  #           Upstream ground truth: unclebob/mutate4go internal/cli/cli.go
  #           (ValidateArgs, consumeValueOption, parsePositiveInt, parseLines).
  #
  # CONTRACT:
  #   command: mutate4py [PATH ...] [options]   (0+ targets: literal paths or
  #            glob patterns; issue #22, ADR 0017)
  #   request — the flag matrix F5 parses and validates:
  #     <targets>            — positional, 0+ PATHs, literal or glob; arity
  #                            decides the run shape: 1 resolved root = today's
  #                            single-file/directory dispatch, 2+ = a union
  #                            batch, 0 = uv workspace autodiscovery (ADR 0017).
  #     --scan               — no-run mode: count sites (F1 surface).
  #     --update-manifest    — no-run mode: rewrite the footer manifest (F2 surface).
  #     --lines L1,L2,...     — selection: comma-separated POSITIVE ints.
  #     --since-last-run      — selection: only changed functions.
  #     --mutate-all          — selection: all covered sites despite manifest.
  #     --mutation-warning N  — positive int, default 50.
  #     --timeout-factor N    — positive int, default 10.
  #     --pytest-args ARGS    — one shell-quoted string of extra pytest arguments,
  #                             default none; reaches pytest directly, never
  #                             through a shell — pytest is the only supported
  #                             runner by contract.
  #     --max-workers N       — positive int, default 0/unset = serial.
  #     --cov-cmd CMD | --lcov PATH | --reuse-coverage — the three coverage flags.
  #     --exclude PATTERN     — repeatable; skip files whose walked path matches the
  #                             shared glob dialect (union across patterns) — the
  #                             same dialect <targets> and uv members/exclude use
  #                             (ADR 0017).
  #     --verbose             — log to stderr.
  #     --help                — print usage, exit 0.
  #   on ACCEPT: parsed options are dispatched —
  #     --scan -> F1 scan surface; --update-manifest -> F2 manifest write;
  #     otherwise -> the F4 run loop (serial, or the F6 worker engine when
  #     --max-workers >= 2 AND sites >= 2). F5 routes; it never re-implements a target.
  #   on REJECT (usage error): a usage/error message is printed and the process exits
  #     NON-ZERO, having run NO analysis and NO test command. Reject classes:
  #     unknown flag, missing value for a value flag, invalid numeric value,
  #     illegal flag combination, a literal target path that does not exist, a
  #     glob pattern matching nothing, zero positionals with no uv workspace
  #     discoverable from cwd upward (ADR 0017).
  #
  # CONSTRAINTS:
  #   - Positive-int flags (--mutation-warning, --timeout-factor, --max-workers) require
  #     an integer >= 1; non-integer or <= 0 is a usage error (parsePositiveInt).
  #   - --lines requires a comma-separated list of POSITIVE integers (parseLines).
  #   - Mutual exclusion (fail-loud, never silent-precedence; ADR 0008):
  #       * --scan and --update-manifest: exclusive of each other AND of every execution
  #         option (--lines, --since-last-run, --mutate-all, non-default --timeout-factor,
  #         a non-empty --pytest-args, --max-workers).
  #       * --since-last-run / --mutate-all / --lines: PAIRWISE exclusive.
  #       * --cov-cmd / --lcov / --reuse-coverage: PAIRWISE exclusive (F3 ADR 0008).
  #   - --max-workers joins ONLY the scan/update-manifest exclusion; it MAY combine with
  #     the selection flags (it does not conflict with --lines/--since-last-run/--mutate-all).
  #   - A literal target path that does not exist, or a glob pattern matching
  #     nothing, is a usage error. Zero positionals is NOT itself a usage error —
  #     it triggers uv workspace autodiscovery; that only errors (exit 2) if no
  #     [tool.uv.workspace] is discoverable climbing from cwd (ADR 0017).
  #   - Defaults when unset: --mutation-warning 50, --timeout-factor 10,
  #     --pytest-args (none), --max-workers serial.
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
  #   - F5 adds no new output strings: --scan / --update-manifest text is F1/F2's,
  #     the run report is F4's. F5 only parses, validates, and routes.
  #   - --help's usage summary must LIST --max-workers (restored).
  #   - The accepted --max-workers count is passed through to the run dispatcher for
  #     F6 to act on; F5 itself does not execute workers.
  #
  # SCOPE:
  #   - Does NOT: execute parallel workers (F6) — F5 validates --max-workers and passes
  #     the count through; the serial/parallel switch and worker engine are F6.
  #   - Does NOT: re-implement --scan counting (F1), --update-manifest writing (F2), the
  #     LCOV gate (F3), or the run loop (F4) — it dispatches to them.
  #   - Does NOT: re-create the --scan / --update-manifest output strings (F1/F2 own
  #     them); F5 only routes to the mode that prints them.
  #   - ASSUMED: the exact arg-parser (argparse vs hand-rolled) and the exact non-zero
  #     exit code (1 vs 2) are the coder's to pin; this feature fixes the usage-error
  #     OUTCOME (message text parameterized, non-zero exit) not the mechanism/code.
  #
  # UX INTENT: none
  # Design artifacts: none

  Background:
    Given an existing Python source file with discovered mutation sites

  # cli-surface-1: every flag in the matrix parses to its option with the documented default
  Scenario Outline: the full flag matrix parses and applies its default
    When I run mutate4py with the flag "<flag>"
    Then the option "<option>" is set to "<value>"
    And the invocation is accepted

    Examples:
      | flag                    | option           | value     |
      | --mutation-warning 25   | mutation-warning | 25        |
      | --timeout-factor 4      | timeout-factor   | 4         |
      | --pytest-args "-x -k foo" | pytest-args   | -x -k foo |
      | --max-workers 4         | max-workers      | 4         |
      | (none)                  | mutation-warning | 50        |
      | (none)                  | timeout-factor   | 10        |
      | (none)                  | pytest-args      | (none)    |
      | (none)                  | max-workers      | serial    |

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
      | --pytest-args      |
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
      | --scan            | --pytest-args "-k foo" |
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

  # cli-surface-7: an unknown flag or a missing source file is a usage error.
  # --test-command is deliberately unrecognized here: it was retired in favor
  # of --pytest-args (issue 03), so it must reject exactly like any other
  # unknown flag, with no special-case handling.
  Scenario Outline: an unknown flag or missing source file is rejected
    When I run mutate4py described by "<invocation>"
    Then the invocation is a usage error
    And the command exits with a non-zero status

    Examples:
      | invocation                        |
      | a valid file with --bogus-flag    |
      | a valid file with --test-command  |
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

  # cli-surface-11: an --exclude match is dropped from the directory walk entirely
  Scenario: an excluded file takes no part in a directory-mode run
    Given a directory holding "keep.py" and "skip.py"
    When I run mutate4py on that directory with "--check-manifest" excluding "**/skip.py"
    Then only "keep.py" is reported

  # cli-surface-12: two or more resolved positional targets run as one union batch (#22)
  Scenario: two file targets run as a single union batch
    Given two Python source files "one.py" and "two.py" without a manifest
    When I run mutate4py on both files with "--check-manifest"
    Then both "one.py" and "two.py" are reported
