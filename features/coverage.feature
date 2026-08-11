# mutation-stamp: sha256=6e6982526b55cea6060c2f783f33594e9f2dd3137f544c5ab1640e23be928074
# acceptance-mutation-manifest-begin
# {"version":1,"tested_at":"2026-07-02T14:16:58.808688Z","feature_name":"Coverage acquisition and the line gate","feature_path":"/Users/gabadi/workspace/addi/mutate4py/features/coverage.feature","background_hash":"341d97015f76800118b02f8fc2eae53ad9d58056a2abce3274d450ae126da206","implementation_hash":"unknown","scenarios":[{"index":0,"name":"a site is covered iff its line has a positive DA count","scenario_hash":"eac213fd71affb40dc285e8eed21fdcfbeb138d4fdabd3bb2ebab5b42010b773","mutation_count":9,"result":{"Total":9,"Killed":9,"Survived":0,"Errors":0},"tested_at":"2026-07-02T04:44:05.003692Z"},{"index":3,"name":"an LCOV SF path matches the target by suffix","scenario_hash":"538cb99467e54f1ad3ba09884544ef59aeccfb8a3be7109227a9c4ffc20d2231","mutation_count":6,"result":{"Total":6,"Killed":6,"Survived":0,"Errors":0},"tested_at":"2026-07-02T04:44:05.003692Z"},{"index":6,"name":"a missing or unusable coverage source exits non-zero and prints no counts","scenario_hash":"c6097e6c450c6b9729127e4b1a1c73bdb73186c46fe8b5a603705ea426f50dd5","mutation_count":4,"result":{"Total":4,"Killed":4,"Survived":0,"Errors":0},"tested_at":"2026-07-02T04:44:05.003692Z"},{"index":7,"name":"supplying more than one coverage flag is a usage error","scenario_hash":"6c9d710d5364bf76980a8f32e58b7e6b6eaa7500a919fc47a2d789e22e332319","mutation_count":3,"result":{"Total":3,"Killed":3,"Survived":0,"Errors":0},"tested_at":"2026-07-02T04:44:05.003692Z"}]}
# acceptance-mutation-manifest-end

Feature: Coverage acquisition and the line gate

  # TRACKING: F3 (coverage-gate) — docs/adr/0007-coverage-default-path-and-line-only-gate.md;
  #           docs/adr/0008-coverage-flags-pairwise-exclusive.md
  #
  # CONTRACT:
  #   command: mutate4py <file> --scan (--cov-cmd <CMD> | --lcov <PATH> | --reuse-coverage)
  #   request:
  #     <file> — path, required; a Python source file with discovered mutation sites (F1).
  #     exactly ONE coverage flag:
  #       --cov-cmd <CMD>   — string; run ONCE (not per site), must emit LCOV.
  #       --lcov <PATH>     — path to a pre-generated LCOV file.
  #       --reuse-coverage  — flag; read LCOV from the default path coverage.lcov.
  #   coverage gate (LINE only):
  #     a site is COVERED iff its line has an LCOV record DA:<line>,<count> with count > 0;
  #     a site is UNCOVERED iff its line is absent from LCOV or has DA count 0;
  #     LCOV SF:<path> is matched to <file> by SUFFIX (one path is a path-suffix of the other);
  #     BRDA (branch) records NEVER affect the gate (ADR 0007).
  #   stdout (exit 0) — the --scan block gains two lines when coverage is supplied:
  #     Mutation scan: <file>
  #     Total mutation sites: <n>
  #     Covered mutation sites: <c>
  #     Uncovered mutation sites: <u>
  #     Manifest exists: <true|false>
  #   response (usage error, non-zero exit, NO partition counts printed):
  #     more than one coverage flag supplied (pairwise-exclusive — ADR 0008);
  #     --reuse-coverage with no file at coverage.lcov;
  #     --lcov pointing at a path with no file.
  #
  # CONSTRAINTS:
  #   - Exactly one coverage flag per run; two or more is a usage error (ADR 0008).
  #   - --cov-cmd runs exactly ONCE for the whole run (acquisition), never per site.
  #   - Gate is LINE coverage only (DA count > 0); BRDA is ignored on purpose so
  #     boundary survivors (> vs >=) are not suppressed (ADR 0007).
  #   - Default path for --reuse-coverage is exactly coverage.lcov (coverage.py's
  #     `coverage lcov` default; ADR 0007).
  #   - Path reconciliation is suffix-based to bridge absolute vs relative SF paths.
  #   - Every discovered site lands in exactly one partition; covered + uncovered == total.
  #   - Coverage lines appear only when a coverage source is supplied; plain --scan
  #     (F1) prints no Covered/Uncovered lines.
  #
  # SEQUENCING:
  #   - Coverage is acquired (cov-cmd run, or LCOV file read) BEFORE sites are partitioned.
  #
  # NFR:
  #   - --cov-cmd is invoked at most once per run (cost paid once, not per site).
  #   - Usage errors (multiple coverage flags, missing LCOV) exit non-zero so CI fails loudly.
  #   - A missing-coverage error tells the user to generate coverage once, not a stack trace.
  #
  # SIDE EFFECTS:
  #   - Coverage acquisition does NOT modify the source file and leaves no
  #     .mutate4py.bak; this slice partitions and prints counts only.
  #   - The acceptance entrypoint generator and step handlers must learn the new steps
  #     (write an LCOV fixture; assert covered/uncovered counts; assert the cov-cmd ran once).
  #   - crap4py's LCOV parser reads BRDA (branch); the DA line-parser and suffix matcher
  #     reuse its SHAPE but are written for DA here (ADR 0007).
  #
  # SCOPE:
  #   - Does NOT: apply mutants, run the per-mutant test, or classify killed/survived/timeout (F4).
  #   - Does NOT: run the baseline test or derive the timeout (F4).
  #   - Does NOT: embed/rewrite the manifest or handle --update-manifest (F2).
  #   - Does NOT: select sites differentially or honor --lines/--since-last-run/--mutate-all (F4).
  #   - Does NOT: own the full flag-matrix validation — F3 specifies the exclusivity
  #     OUTCOME (non-zero exit, no counts); F5 owns where in the parse pipeline it fires,
  #     and whether --scan + a coverage flag is permitted (ADR 0008).
  #   - Does NOT: parallelize (--max-workers is parsed in F5, executed in F6 on the
  #     parallel path).
  #   - ASSUMED: an LCOV file supplied to the tool is well-formed; malformed-LCOV handling
  #     is not specified here (flag if field use shows it matters).
  #   - ASSUMED: --cov-cmd writes its LCOV to a location the tool then reads; the exact
  #     emit-path contract is the coder's to pin against the injected exec seam.
  #
  # UX INTENT: none
  # Design artifacts: none

  Background:
    Given a Python source file with mutation sites on lines "3,5,7"

  # coverage-1: the line gate partitions each site by its DA hit count
  Scenario Outline: a site is covered iff its line has a positive DA count
    Given an LCOV file covering lines "<covered>" for that source
    When I run mutate4py scanning with coverage "--lcov cov.info"
    Then the output line "Total mutation sites: 3" is printed
    And the output line "Covered mutation sites: <coveredCount>" is printed
    And the output line "Uncovered mutation sites: <uncoveredCount>" is printed

    Examples:
      | covered | coveredCount | uncoveredCount |
      | 3,5,7   | 3            | 0              |
      | 3,7     | 2            | 1              |
      |         | 0            | 3              |

  # coverage-2: a line present in LCOV with a zero hit count is uncovered
  Scenario: a DA count of zero is uncovered, not covered
    Given an LCOV file with the single record "DA:5,0" for that source
    When I run mutate4py scanning with coverage "--lcov cov.info"
    Then the output line "Covered mutation sites: 0" is printed
    And the output line "Uncovered mutation sites: 3" is printed

  # coverage-3: branch (BRDA) data never affects the gate
  Scenario: a line with only branch data and no positive DA hit is uncovered
    Given an LCOV file whose only record for line 5 is branch data "BRDA:5,0,0,1"
    When I run mutate4py scanning with coverage "--lcov cov.info"
    Then the output line "Covered mutation sites: 0" is printed
    And the output line "Uncovered mutation sites: 3" is printed

  # coverage-4: SF path is matched to the source by suffix (absolute vs relative)
  Scenario Outline: an LCOV SF path matches the target by suffix
    Given an LCOV file covering line 5 under the SF path "<sfPath>" for that source
    When I run mutate4py scanning with coverage "--lcov cov.info"
    Then the output line "Covered mutation sites: <coveredCount>" is printed

    Examples:
      | sfPath          | coveredCount |
      | absolute-suffix | 1            |
      | relative-suffix | 1            |
      | unrelated-file  | 0            |

  # coverage-5: --cov-cmd runs once and its emitted LCOV drives the partition
  Scenario: --cov-cmd is run exactly once to acquire coverage
    Given a coverage command that emits an LCOV file covering line 5
    When I run mutate4py scanning with coverage "--cov-cmd CMD"
    Then the coverage command runs exactly once
    And the output line "Covered mutation sites: 1" is printed

  # coverage-6: --reuse-coverage reads the default path coverage.lcov when present
  Scenario: --reuse-coverage reads coverage.lcov without regenerating
    Given an LCOV file at the default path "coverage.lcov" covering lines "5" for that source
    When I run mutate4py scanning with coverage "--reuse-coverage"
    Then the output line "Covered mutation sites: 1" is printed
    And the coverage command runs exactly 0 times

  # coverage-7: a coverage-acquisition failure is a hard usage error with no counts
  Scenario Outline: a missing or unusable coverage source exits non-zero and prints no counts
    Given there is no readable LCOV at "<missing>"
    When I run mutate4py scanning with coverage "<flag>"
    Then the command exits with a non-zero status
    And no partition counts are printed

    Examples:
      | flag                | missing       |
      | --reuse-coverage    | coverage.lcov |
      | --lcov missing.info | missing.info  |

  # coverage-8: the three coverage flags are pairwise-exclusive
  Scenario Outline: supplying more than one coverage flag is a usage error
    When I run mutate4py scanning with coverage "<flags>"
    Then the command exits with a non-zero status
    And no partition counts are printed

    Examples:
      | flags                            |
      | --lcov cov.info --reuse-coverage |
      | --cov-cmd CMD --lcov cov.info    |
      | --cov-cmd CMD --reuse-coverage   |

  # coverage-9: coverage acquisition never modifies the source
  Scenario: scanning with coverage leaves the source byte-identical and no backup
    Given an LCOV file covering lines "3,5,7" for that source
    When I run mutate4py scanning with coverage "--lcov cov.info"
    Then the source file is byte-for-byte unchanged
    And no ".mutate4py.bak" file is left behind
