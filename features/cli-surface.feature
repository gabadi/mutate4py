# mutation-stamp: sha256=e6b1764aaa80fd878c44b584f4261cb2b08c17ff54e2e7fbf4081f792a92a2a5
# acceptance-mutation-manifest-begin
# {"version":1,"tested_at":"2026-10-11T14:06:30Z","feature_name":"The CLI surface parses, validates, and dispatches the flag matrix","feature_path":"/Users/gabadi/workspace/gabadi/saga-umf-integration/features/cli-surface.feature","background_hash":"1203275c6eabf9fc410f98f69ac6af108b327191aeca7b251b7f196f4d6e6eaf","implementation_hash":"unknown","scenarios":[{"index":0,"name":"the full flag matrix parses and applies its default","scenario_hash":"03a45905d699c48c6d3ab4c588d38c285e7353d10a0609b717cf383da1710c81","mutation_count":24,"result":{"Total":24,"Killed":24,"Survived":0,"Errors":0},"tested_at":"2026-10-11T12:12:22Z"},{"index":1,"name":"a numeric flag rejects values that are not positive integers","scenario_hash":"a2c7162b81dcdd3a79f489b3256f997b25d42a9660d3d68e859394d9502ef2ef","mutation_count":11,"result":{"Total":11,"Killed":11,"Survived":0,"Errors":0},"tested_at":"2026-10-11T12:12:22Z"},{"index":2,"name":"a value flag with a missing value is rejected","scenario_hash":"eb241ea0cba61ffc586de2a488c2c5f249bf8ec8da16a46161fc8a6c90bd4891","mutation_count":5,"result":{"Total":5,"Killed":5,"Survived":0,"Errors":0},"tested_at":"2026-10-11T12:12:22Z"},{"index":3,"name":"a no-run mode rejects being combined with an execution option","scenario_hash":"690c16913b191b40779ab87ff3a72eb23385a9372c00658ac17cb501cda65669","mutation_count":48,"result":{"Total":48,"Killed":48,"Survived":0,"Errors":0},"tested_at":"2026-10-11T12:12:22Z"},{"index":4,"name":"combining two selection flags is a usage error","scenario_hash":"88ff433e01244df649696d2076a6a8a2df4ee1a22f323d8c51400cb49ac80335","mutation_count":6,"result":{"Total":6,"Killed":6,"Survived":0,"Errors":0},"tested_at":"2026-10-11T12:12:22Z"},{"index":5,"name":"--max-workers is accepted alongside a selection flag","scenario_hash":"3ab1c84ab1c02366f62e18afb506789995ccc145af73681ae21b8cf9fff416f1","mutation_count":3,"result":{"Total":3,"Killed":3,"Survived":0,"Errors":0},"tested_at":"2026-10-11T12:12:22Z"},{"index":6,"name":"an unknown flag or missing source file is rejected","scenario_hash":"74249d8a7e4085565d2eb0bbd14061efd2b0c7f69744de75a20af3c40c556ffc","mutation_count":4,"result":{"Total":4,"Killed":4,"Survived":0,"Errors":0},"tested_at":"2026-10-11T12:12:22Z"},{"index":7,"name":"--help short-circuits to usage even with invalid args","scenario_hash":"0f1c3f6768d7f821b590a1d9f8f3b9e9876f4f5dd78ef8813db0d5c33da45a2c","mutation_count":3,"result":{"Total":3,"Killed":3,"Survived":0,"Errors":0},"tested_at":"2026-10-11T12:12:22Z"},{"index":8,"name":"validated options are routed to the right behaviour","scenario_hash":"2053e21dff52520290af1b4bcd55de386ea5b0ad7ba405b96dcf62a575f6e11b","mutation_count":6,"result":{"Total":6,"Killed":6,"Survived":0,"Errors":0},"tested_at":"2026-10-11T12:12:22Z"}]}
# acceptance-mutation-manifest-end

Feature: The CLI surface parses, validates, and dispatches the flag matrix

  # TRACKING: F5 (cli-surface) — docs/adr/0015-parallel-workers-via-uv-clone-per-worker.md;
  #           docs/adr/0027-single-session-ctrace-measurement-unit-only-scoring.md (the coverage flags are removed)
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
  #     --mutation-warning N  — positive int, default 50.
  #     --timeout-factor N    — positive int, default 10.
  #     --pytest-args ARGS    — one shell-quoted string of extra pytest arguments,
  #                             default none; reaches pytest directly, never
  #                             through a shell — pytest is the only supported
  #                             runner by contract.
  #     --max-workers N       — positive int, default 0/unset = serial.
  #     --cov-cmd CMD | --lcov PATH | --reuse-coverage | --test-contexts DB |
  #     --build-test-contexts OUT — REMOVED in 0.3.0: each exits 2
  #                             with "<flag> removed in 0.3.0: the run measures coverage
  #                             itself" (refusal scenarios live in coverage.feature).
  #     --lines L | --since-last-run | --mutate-all — REMOVED in 0.3.0: each exits 2 the same
  #                             way, naming the flag and its replacement (refusal scenarios:
  #                             cli-surface-5). --mutate-all is removed by spec #115: the
  #                             default run already scores every changed or Unscored function.
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
  #   - Mutual exclusion (fail-loud, never silent-precedence):
  #       * --scan and --update-manifest: exclusive of each other AND of every execution
  #         option (non-default --timeout-factor, a non-empty --pytest-args,
  #         --max-workers).
  #   - The removed selection flags (--lines, --since-last-run, --mutate-all) are refused,
  #     never ignored (cli-surface-5). That refusal is checked before the exclusion check.
  #   - --max-workers joins ONLY the scan/update-manifest exclusion; a default scored run
  #     takes it.
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
  #     coverage gate (F3), or the run loop (F4) — it dispatches to them.
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

  # cli-surface-1 (removed, #125): its rows only checked that a flag was accepted, which
  # no scenario can fail on. Parsing and defaults are pinned in-process by
  # tests/test_main_cli_flags.py (--mutation-warning, --timeout-factor and --min-timeout,
  # --pytest-args, --max-workers) and the flags' reach into the run by
  # tests/test_dispatch.py::test_run_on_file_wires_args_into_run_mutations. The effects
  # acceptance can see are asserted where they happen: run-loop-9 (--mutation-warning),
  # site-discovery-5 (--mutation-warning on --scan), parallel-workers-1 and cli-surface-10
  # (--max-workers), test-selection (--pytest-args verbatim).

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

  # cli-surface-4: --scan and --update-manifest reject every execution option
  Scenario Outline: a no-run mode rejects being combined with an execution option
    When I run mutate4py with "<mode>" and "<other>"
    Then the invocation is a usage error
    And the command exits with a non-zero status

    Examples:
      | mode              | other             |
      | --scan            | --update-manifest |
      | --scan            | --timeout-factor 5 |
      | --scan            | --pytest-args "-k foo" |
      | --scan            | --max-workers 4   |
      | --update-manifest | --scan            |
      | --update-manifest | --max-workers 4   |
      | --scan            | --allow-survivors |
      | --update-manifest | --allow-survivors |
      | --check-manifest  | --allow-survivors |

  # cli-surface-4b: a rejected invocation does no work: it names the problem,
  # leaves the source byte-identical and creates no backup
  Scenario Outline: a rejected invocation exits non-zero and leaves the source untouched
    When I run the rejected invocation "<invocation>"
    Then the command exits with a non-zero status
    And the printed output names the offending flag or combination
    And the source file is byte-identical to before the run
    And no ".mutate4py.bak" file was created

    Examples:
      | invocation                     |
      | --mutation-warning 0           |
      | --max-workers -1               |
      | --timeout-factor 1.5           |
      | --lines 7                      |
      | --scan --max-workers 4         |
      | --update-manifest --lines 7    |
      | --since-last-run               |
      | --mutate-all                   |
      | --bogus-flag                   |
      | (a path that does not exist)   |
      | (no source file argument)      |
      | --max-workers (with no value)  |

  # cli-surface-5: the selection flags removed in 0.3.0 are refused, not ignored: each is a
  # usage error that runs no analysis. The refusal wording is pinned by
  # tests/test_removed_selection_flags.py.
  Scenario Outline: a selection flag removed in 0.3.0 is a usage error
    When I run mutate4py with the flag "<flag>"
    Then the invocation is a usage error
    And the command exits with a non-zero status
    And no analysis or test run occurs

    Examples:
      | flag             |
      | --lines 7        |
      | --since-last-run |
      | --mutate-all     |

  # cli-surface-6: --max-workers is accepted on the default scored run. --mutate-all is
  # removed (spec #115), so no selection flag remains to combine with --max-workers.
  Scenario: --max-workers is accepted on the default scored run
    When I run mutate4py with the accepted flags "--max-workers 4 (a scored run)"
    Then the invocation is accepted

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
      | --mutate-all        |

  # cli-surface-9: an accepted invocation dispatches to the matching mode
  Scenario Outline: validated options are routed to the right behaviour
    When I run mutate4py with the accepted flags "<flags>"
    Then the run is dispatched to the "<target>" behaviour

    Examples:
      | flags             | target          |
      | --scan            | scan surface    |
      | --update-manifest | manifest write  |
      | (a scored run) | run loop        |

  # cli-surface-10: the accepted --max-workers count reaches the run, which reports it
  Scenario: an accepted --max-workers count is reported by the run
    When I run mutate4py with the accepted flags "--max-workers 4 (a scored run)"
    Then the run is dispatched to the "run loop" behaviour
    And the run reports a worker count of "4"

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

  # cli-surface-15: a scored run whose project .venv is not the running
  # interpreter is rejected before any Baseline starts (ADR 0025;
  # a foreign interpreter otherwise fails at the
  # Baseline with an uninformative "exit code 2")
  Scenario: a run from outside the project environment is rejected before any baseline
    Given a project with a ".venv" that the running interpreter is not
    When I run mutate4py with the accepted flags "(a scored run)" from outside that environment
    Then the command exits with status "2"
    And the error names the running interpreter and the project environment
    And no baseline pytest run is started

  # cli-surface-15 positive control: the same project without a ".venv" passes
  # the startup check and starts its Baseline, so the "no baseline" assertion
  # above is not satisfied vacuously.
  Scenario: the same project without a ".venv" starts its baseline
    Given a project with no ".venv"
    When I run mutate4py with the accepted flags "(a scored run)" from that project
    Then a baseline pytest run is started
