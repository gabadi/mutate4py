# acceptance-mutation-manifest-begin
# {"version":1,"tested_at":"2026-06-29T05:44:27.546312Z","feature_name":"The mutation run loop and report","feature_path":"/Users/gabadi/workspace/addi/mutate4py/features/run-loop.feature","background_hash":"1dd133df71819ac82cc0542649edb76c526b89f2510b6d55591dcaf624a517b7","implementation_hash":"unknown","scenarios":[{"index":1,"name":"the report tallies killed, survived, and uncovered","scenario_hash":"12cd32c4597148d5128e55ef3ad3c896f6ebb6ad1f654325460a27669518c56d","mutation_count":18,"result":{"Total":18,"Killed":18,"Survived":0,"Errors":0},"tested_at":"2026-06-29T05:44:27.546312Z"},{"index":3,"name":"the mutant timeout is derived from the baseline duration","scenario_hash":"2feaeab63069abb2092081d72eab50f0272e9ba79c6f3e5fe0e3434d96c6ae95","mutation_count":6,"result":{"Total":6,"Killed":6,"Survived":0,"Errors":0},"tested_at":"2026-06-29T05:44:27.546312Z"},{"index":5,"name":"effectiveSinceLastRun decides which covered sites are selected","scenario_hash":"a75c132f8a0ab35ab7c4f28b8eda86d6c719960eb51318b3041d5fc2a1da214e","mutation_count":16,"result":{"Total":16,"Killed":16,"Survived":0,"Errors":0},"tested_at":"2026-06-29T05:44:27.546312Z"},{"index":6,"name":"the uncovered block visibility follows the differential switch","scenario_hash":"cc1bf54068aee1f2a5506762562a26b3474c2676e54ed599b3a00bd063972c8c","mutation_count":12,"result":{"Total":12,"Killed":12,"Survived":0,"Errors":0},"tested_at":"2026-06-29T05:44:27.546312Z"},{"index":8,"name":"the over-threshold warning is conditional","scenario_hash":"b3de9810d9103a0fcbe4f82820857a8a4560dbcdb4c860bd3063426b79c00dea","mutation_count":6,"result":{"Total":6,"Killed":6,"Survived":0,"Errors":0},"tested_at":"2026-06-29T05:44:27.546312Z"}]}
# acceptance-mutation-manifest-end

Feature: The mutation run loop and report

  # TRACKING: F4 (run-loop) — docs/plan.md; docs/spec.md §7 (run loop), §8 (output),
  #           §9 (serial path; parallelism reopened as F6 — ADR 0013/0015);
  #           CONTEXT.md "Run loop & report (F4)";
  #           docs/adr/0010-run-loop-composes-f3-coverage-and-baseline-gate.md;
  #           docs/adr/0011-timeout-printed-verbatim-folded-into-killed.md;
  #           docs/adr/0012-run-loop-serial-only-no-worker-token.md
  #           Upstream ground truth: unclebob/mutate4go internal/runner/runner.go
  #           (Mutate, runMutationsSerial, runMutant, summarize, printHeader).
  #
  # CONTRACT:
  #   command: mutate4py <file> [--test-command CMD] [--timeout-factor N]
  #            [--lines L,...] [--since-last-run] [--mutate-all] [--mutation-warning N]
  #            <one coverage flag: --cov-cmd CMD | --lcov PATH | --reuse-coverage>
  #   request:
  #     <file> — path, required; a Python source file with discovered mutation sites (F1).
  #     --test-command CMD — string, default "pytest"; the suite run for baseline and per mutant.
  #     --timeout-factor N — positive int, default 10; mutant timeout = max(1s, N × baseline).
  #     selection flags (--lines / --since-last-run / --mutate-all) — already parsed (F5 validates).
  #   run order (observable): strip manifest -> discover -> build+diff manifest ->
  #     acquire coverage (F3) + partition -> select -> print header -> [uncovered block] ->
  #     baseline -> save .mutate4py.bak -> per-site apply/test/classify/restore ->
  #     restore source -> print report -> re-embed manifest -> remove .mutate4py.bak.
  #   stdout (exit 0) — the §8 run output:
  #     [Restored source from backup (previous run was interrupted).]   (only if a .bak existed)
  #     [Reusing existing coverage; covered/uncovered classification may be stale.]  (only --reuse-coverage)
  #     Mutation run: <file>
  #     Total mutation sites: <n>
  #     Covered mutation sites: <c>
  #     Uncovered mutation sites: <u>
  #     Changed mutation sites: <ch>
  #     Manifest exists: <true|false>
  #     Selected mutation sites: <s>
  #     [Warning: <n> mutation sites exceeds threshold <m>.]            (only when n > m)
  #     [Uncovered mutations: / "  line <L> <desc> <functionID>" ...]   (only when not differential and no --lines)
  #     [i/total] <status> line <L> <orig> -> <mutant>: <functionID>    (one per selected site)
  #     (blank line)
  #     Mutation Report
  #     ===============
  #     Killed: <killed+timeout>
  #     Survived: <survived>
  #     Uncovered: <u>
  #     [Survivors: / "  line <L> <desc> <functionID>" ...]             (only when survived > 0)
  #   response (baseline failure, non-zero exit): "baseline failed: <reason>";
  #     no mutant applied, no .mutate4py.bak left, no report printed.
  #   NOT in the response (F4 default, --max-workers unset/0): no "Mutation workers: <n>"
  #     line; no "worker-<k>" token; no "Timeout: <n>" report line (timeout folds into
  #     Killed). NOTE (F6, ADR 0012 amendment/0015): a serial run with --max-workers > 0
  #     DOES print "Mutation workers: <n>" (upstream-verbatim, runner.go:614); the
  #     "worker-<k>" token is still absent on any serial run. F4 scenarios cover the
  #     --max-workers-unset case; the workers line is exercised in F6 (parallel-workers).
  #
  # CONSTRAINTS:
  #   - <status> per mutant is exactly one of: killed (non-zero exit), timeout (exceeded
  #     the mutant timeout), survived (zero exit). timeout prints verbatim per-mutant and
  #     is added to Killed in the report (ADR 0011).
  #   - <desc> is "<original> -> <mutant>" (the site's mutation description).
  #   - The per-mutant line has a colon before <functionID>; the uncovered and survivor
  #     lines do not (ADR 0011): per-mutant "<desc>: <functionID>" vs "  line <L> <desc> <functionID>".
  #   - mutant timeout = max(1s, timeout-factor × baseline-duration); the 1s floor is fixed.
  #   - effectiveSinceLastRun = --since-last-run OR (manifest exists AND not --mutate-all
  #     AND not --lines). Differential is the default once a manifest exists.
  #   - The uncovered block prints only when NOT differential AND no --lines.
  #   - Survivors block prints only when survived > 0.
  #   - Killed report total = killed-count + timeout-count.
  #   - The run is serial: sites are mutated one at a time in stable (line, column) order;
  #     no parallel workers run on this path (§9, ADR 0012). The parallel engine selected
  #     by --max-workers >= 2 AND >= 2 sites is F6 (parallel-workers, ADR 0015).
  #
  # SEQUENCING:
  #   - Coverage is acquired and sites partitioned BEFORE the baseline runs.
  #   - The baseline runs BEFORE any mutant is applied and BEFORE .mutate4py.bak is saved;
  #     a baseline failure therefore leaves no backup.
  #   - Each site is restored to the original BEFORE the next site is mutated.
  #   - The source is restored and the report printed BEFORE the fresh manifest is re-embedded.
  #   - A pre-existing .mutate4py.bak is restored at run START, before discovery.
  #
  # NFR:
  #   - The baseline and each mutant run the test command exactly once; per-mutant runs
  #     are bounded by the mutant timeout so a hung mutant cannot stall the run.
  #   - A baseline failure exits non-zero so CI fails loudly and no misleading report prints.
  #   - On any interruption the next run self-heals from .mutate4py.bak before doing work.
  #
  # SIDE EFFECTS:
  #   - The run mutates the source file in place during the loop, then restores it and
  #     re-embeds a fresh manifest; the only persistent change to <file> is the updated
  #     manifest footer. .mutate4py.bak exists only during the loop.
  #   - The acceptance entrypoint generator and step handlers must learn the new steps:
  #     a fake test command whose pass/fail/sleep is scripted per mutant; assert ordered
  #     stdout blocks; assert .mutate4py.bak presence/absence; assert the restored source.
  #
  # SCOPE:
  #   - Does NOT: parse or validate CLI flags, mutual-exclusion, or numeric ranges (F5);
  #     it consumes already-parsed options.
  #   - Does NOT: own --scan or --update-manifest output (F1/F2); does NOT re-implement
  #     site discovery (F1), manifest embed/diff (F2), or the LCOV line gate (F3).
  #   - Does NOT: print a "worker-<k>" token or a "Timeout:" report line; does NOT
  #     parallelize — the serial path only (§9, ADR 0012). Does NOT print a "Mutation
  #     workers" line in the F4 default case (--max-workers unset/0); the workers line
  #     for --max-workers > 0 and the parallel engine are F6 (§9 reopened, ADR 0013/0015).
  #     Parsing --max-workers is F5.
  #   - ASSUMED: the injected exec seam runs --test-command via the shell and reports exit
  #     status and timeout; the exact subprocess mechanism is the coder's to pin.
  #   - ASSUMED: a coverage source is supplied (F3); a run with no coverage flag is an F5
  #     validation concern, not specified here.
  #
  # UX INTENT: none
  # Design artifacts: none

  Background:
    Given a Python source file with covered mutation sites
    And a baseline test command that passes

  # run-loop-1: a mutant is classified by the mutated test run's outcome
  Scenario Outline: the mutated test run outcome decides the status
    Given the mutated test run will "<outcome>"
    When I run mutate4py mutating that file
    Then the progress line for that mutant shows status "<status>"
    And the report counts that mutant as "<tally>"

    Examples:
      | outcome      | status   | tally   |
      | exit nonzero | killed   | Killed  |
      | exceed timeout | timeout | Killed  |
      | exit zero    | survived | Survived |

  # run-loop-2: the report folds timeout into Killed and lists only survivors
  Scenario Outline: the report tallies killed, survived, and uncovered
    Given <killed> mutants exit nonzero and <timed> time out and <survived> exit zero
    And there are <uncovered> uncovered sites
    When I run mutate4py mutating that file
    Then the output line "Killed: <killedTotal>" is printed
    And the output line "Survived: <survived>" is printed
    And the output line "Uncovered: <uncovered>" is printed
    And a "Survivors:" block is printed only when "<hasSurvivors>" is "yes"

    Examples:
      | killed | timed | survived | uncovered | killedTotal | hasSurvivors |
      | 2      | 1     | 0        | 0         | 3           | no           |
      | 1      | 0     | 2        | 1         | 1           | yes          |
      | 0      | 2     | 0        | 0         | 2           | no           |

  # run-loop-3: the per-mutant line is verbatim with a colon before the function id
  Scenario: the per-mutant progress line is the verbatim upstream format
    Given a single selected site on line 7 in function "func/calc" mutating "a > b" to "a >= b"
    And that mutant exits nonzero
    When I run mutate4py mutating that file
    Then the output line "[1/1] killed line 7 a > b -> a >= b: func/calc" is printed

  # run-loop-4: the mutant timeout is timeout-factor times the baseline, floored at 1s
  Scenario Outline: the mutant timeout is derived from the baseline duration
    Given the baseline takes "<baseline>" to pass
    And the timeout factor is "<factor>"
    When I run mutate4py mutating that file
    Then the mutant timeout is "<timeout>"

    Examples:
      | baseline | factor | timeout |
      | 2s       | 10     | 20s     |
      | 10ms     | 10     | 1s      |

  # run-loop-5: a failing baseline aborts the run before any mutant
  Scenario: a failing baseline aborts with no mutant applied and no backup
    Given the baseline test command fails
    When I run mutate4py mutating that file
    Then the command exits with a non-zero status
    And the output contains "baseline failed:"
    And no mutant was applied
    And no ".mutate4py.bak" file is left behind
    And no "Mutation Report" is printed

  # run-loop-6: differential selection is the default once a manifest exists
  Scenario Outline: effectiveSinceLastRun decides which covered sites are selected
    Given the file "<hasManifest>" an existing manifest
    And the flags supplied are "<flags>"
    When I run mutate4py mutating that file
    Then the run "<isDifferential>" differential
    And only "<selected>" sites are selected

    Examples:
      | hasManifest | flags           | isDifferential | selected         |
      | has         |                 | is             | changed-function |
      | has         | --mutate-all    | is not         | all-covered      |
      | has not     |                 | is not         | all-covered      |
      | has         | --since-last-run | is            | changed-function |

  # run-loop-7: the uncovered block prints only on a non-differential run with no --lines
  Scenario Outline: the uncovered block visibility follows the differential switch
    Given the file "<hasManifest>" an existing manifest
    And the flags supplied are "<flags>"
    And there is at least one uncovered site
    When I run mutate4py mutating that file
    Then an "Uncovered mutations:" block "<visibility>" printed

    Examples:
      | hasManifest | flags        | visibility  |
      | has not     |              | is          |
      | has         |              | is not      |
      | has         | --mutate-all | is          |
      | has not     | --lines 7    | is not      |

  # run-loop-8: the header reports the six counts with no workers line
  Scenario: the run header prints the count lines and never a workers line
    When I run mutate4py mutating that file
    Then the output line "Mutation run:" is printed
    And the output lines "Total mutation sites:", "Covered mutation sites:", "Uncovered mutation sites:", "Changed mutation sites:", "Manifest exists:", "Selected mutation sites:" are printed
    And no "Mutation workers:" line is printed
    And no "worker-" token appears in any progress line

  # run-loop-9: the warning line prints only when total sites exceed the threshold
  Scenario Outline: the over-threshold warning is conditional
    Given the file has "<total>" total mutation sites
    And the mutation warning threshold is "<threshold>"
    When I run mutate4py mutating that file
    Then a "Warning: <total> mutation sites exceeds threshold <threshold>." line "<visibility>" printed

    Examples:
      | total | threshold | visibility |
      | 51    | 50        | is         |
      | 50    | 50        | is not     |

  # run-loop-10: the source is restored and a fresh manifest re-embedded after the report
  Scenario: the run restores the source and re-embeds the manifest
    When I run mutate4py mutating that file
    Then after the run the source has no mutant spliced in
    And the source ends with a fresh "mutate4py-manifest" footer
    And no ".mutate4py.bak" file is left behind

  # run-loop-11: a leftover backup from an interrupted run is restored first
  Scenario: a pre-existing backup is restored at the start of the next run
    Given a ".mutate4py.bak" file exists from a previous interrupted run
    When I run mutate4py mutating that file
    Then the output line "Restored source from backup (previous run was interrupted)." is printed
    And the source matches the backup before discovery proceeds

  # run-loop-12: --reuse-coverage prints the stale-coverage warning before the header
  Scenario: reusing coverage warns that the classification may be stale
    Given a readable LCOV file at the default coverage path
    When I run mutate4py mutating that file with "--reuse-coverage"
    Then the output line "Reusing existing coverage; covered/uncovered classification may be stale." is printed
    And that line appears before the "Mutation run:" line
