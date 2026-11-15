# mutation-stamp: sha256=fae90f179060d4971b051b7e9039d54a5cafdb93388c3ae4d04e2f25eae02668
# acceptance-mutation-manifest-begin
# {"version":1,"tested_at":"2026-10-11T14:06:30Z","feature_name":"Coverage acquisition and the line gate","feature_path":"/Users/gabadi/workspace/gabadi/saga-umf-integration/features/coverage.feature","background_hash":"341d97015f76800118b02f8fc2eae53ad9d58056a2abce3274d450ae126da206","implementation_hash":"unknown","scenarios":[{"index":0,"name":"a site is covered iff its line has a positive DA count","scenario_hash":"4487771ac1e43d7f239098b542487d65ada5739e0e23ea8597e9e05f9bdf1326","mutation_count":9,"result":{"Total":9,"Killed":9,"Survived":0,"Errors":0},"tested_at":"2026-10-11T07:28:37Z"},{"index":3,"name":"an LCOV SF path matches the target by suffix","scenario_hash":"5047dd5d5c51b72d8cc33e2eabb695293b3d687cf7c8eb7928745d613adfe706","mutation_count":6,"result":{"Total":6,"Killed":6,"Survived":0,"Errors":0},"tested_at":"2026-10-11T07:28:37Z"},{"index":6,"name":"a missing or unusable coverage source exits non-zero and prints no counts","scenario_hash":"a67e5df4cfa047d2b46f4a0167161dfcfdd52cf312eafc90d56094b42c00faf4","mutation_count":4,"result":{"Total":4,"Killed":4,"Survived":0,"Errors":0},"tested_at":"2026-10-11T07:28:37Z"},{"index":7,"name":"supplying more than one coverage flag is a usage error","scenario_hash":"8c72f077f5eff1721905352edd9f392dc953579838eda999bcabd00069fda4ad","mutation_count":3,"result":{"Total":3,"Killed":3,"Survived":0,"Errors":0},"tested_at":"2026-10-11T07:28:37Z"}]}
# acceptance-mutation-manifest-end

Feature: Measurement as coverage, the core refusal, removed flags

  # TRACKING: F3 (coverage-gate) — docs/adr/0027-single-session-ctrace-measurement-unit-only-scoring.md;
  #           docs/adr/0007-coverage-default-path-and-line-only-gate.md (the line-only gate);
  #           docs/adr/0008-coverage-flags-pairwise-exclusive.md (superseded: the flags are removed)
  #
  # CONTRACT:
  #   command: mutate4py <file> --pytest-args ARGS
  #   A scored run measures coverage itself: one pytest session under coverage.py's
  #   ctrace core runs the project's unit tests (the Measurement, ADR 0027). Its data
  #   gives the Baseline, the Coverage gate and the Test map. No coverage file is read.
  #   coverage gate (LINE only):
  #     a site is COVERED iff some test context reached its line, the Empty context
  #     (lines run while conftests and plugins load) included; a site is UNCOVERED
  #     otherwise. Branch coverage never affects the gate (ADR 0007).
  #   stdout (exit 0) — the run header carries the partition:
  #     Mutation run: <file>
  #     Total mutation sites: <n>
  #     Covered mutation sites: <c>
  #     Uncovered mutation sites: <u>
  #   the core: the session runs with COVERAGE_CORE=ctrace whatever the caller's
  #     environment asks for. A run whose effective core reads back as sysmon exits 2
  #     (covered by the unit tests, which can stub the core; no feature can force it).
  #   removed flags: --cov-cmd, --lcov, --reuse-coverage, --test-contexts and
  #     --build-test-contexts were removed in 0.3.0. Each
  #     exits 2 with "<flag> removed in 0.3.0: the run measures coverage itself", prints
  #     no partition counts, runs no test and leaves the source and its backup alone.
  #   --scan stays coverage-free: it prints the Total line and no Covered/Uncovered lines.
  #
  # CONSTRAINTS:
  #   - Every discovered site lands in exactly one partition; in a full run covered + uncovered == total.
  #     A differential run counts the uncovered sites of the changed functions only (the Run scope).
  #   - Gate is LINE coverage only, so boundary survivors (> vs >=) are not suppressed (ADR 0007).
  #   - Coverage comes only from the Measurement: there is no coverage file, command or reuse path.
  #
  # SEQUENCING:
  #   - The Measurement runs BEFORE sites are partitioned and before any Mutant.
  #
  # SCOPE:
  #   - Does NOT: classify killed/survived/timeout (run-loop.feature).
  #   - Does NOT: cover test selection by the Test map (test-selection.feature).
  #   - Does NOT: reach the sysmon refusal end to end: the core is forced, so no project
  #     can make a run read back sysmon; the refusal is a unit-tested guard.
  #
  # UX INTENT: none
  # Design artifacts: none

  Background:
    Given a pytest project whose module has three comparison sites in functions f1, f2 and f3

  # coverage-1: the line gate partitions each site by whether a test reached its line
  Scenario Outline: a site is covered iff a test reached its line
    Given the tests call "<called>"
    When I run mutate4py on that source with its tests
    Then the output line "Total mutation sites: 3" is printed
    And the output line "Covered mutation sites: <coveredCount>" is printed
    And the output line "Uncovered mutation sites: <uncoveredCount>" is printed

    Examples:
      | called   | coveredCount | uncoveredCount |
      | f1,f2,f3 | 3            | 0              |
      | f1,f3    | 2            | 1              |
      |          | 0            | 3              |

  # coverage-2: a line run while a conftest loads is covered (the Empty context)
  Scenario: a site run at import time, before any test starts, is covered
    Given a module whose only site is a module-level line that no test calls
    And a conftest that imports the module while pytest loads it
    When I run mutate4py on that source with its tests
    Then the output line "Total mutation sites: 2" is printed
    And the output line "Covered mutation sites: 2" is printed
    And the output line "Uncovered mutation sites: 0" is printed

  # coverage-3: branch coverage never affects the gate: the comparison line ran, so it
  # is covered even though its true arm never did; only the arm's own line is uncovered
  Scenario: a line reached by a half-taken branch is covered
    Given a function whose comparison sits in a branch that the tests take only one way
    When I run mutate4py on that source with its tests
    Then the output line "Total mutation sites: 3" is printed
    And the output line "Covered mutation sites: 2" is printed
    And the output line "Uncovered mutation sites: 1" is printed
    And the output line "  line 3 1 -> 0 func/f1" is printed

  # coverage-4: the Measurement forces the ctrace core
  Scenario: the tests run under ctrace whatever core the caller asks for
    Given a test that records the coverage core it ran under
    And the caller's environment asks for the "sysmon" core
    When I run mutate4py on that source with its tests
    Then the first run of the tests saw the "ctrace" core

  # coverage-5: each removed coverage or test-context flag is refused with the replacement message
  Scenario Outline: a removed flag exits 2 and says the run measures coverage itself
    When I run mutate4py on that source with the removed flag "<flag>"
    Then the command exits with status "2"
    And the output names the refusal of "<flag>"
    And no partition counts are printed
    And the source file is byte-for-byte unchanged
    And no ".mutate4py.bak" file is left behind

    Examples:
      | flag            |
      | --cov-cmd CMD   |
      | --lcov cov.info |
      | --reuse-coverage |
      | --test-contexts DB |
      | --build-test-contexts OUT |

  # coverage-6: --scan stays coverage-free
  Scenario: scanning prints the total and no coverage partition
    When I scan that source
    Then the output line "Total mutation sites: 3" is printed
    And no partition counts are printed
    And the source file is byte-for-byte unchanged
    And no ".mutate4py.bak" file is left behind
