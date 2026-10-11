# mutation-stamp: sha256=44f9670e805118f7a7761e23089501da366822a30c4ce7992fabf5c9f5c6dac2
# acceptance-mutation-manifest-begin
# {"version":1,"tested_at":"2026-10-11T07:48:07Z","feature_name":"Parallel worker execution for --max-workers","feature_path":"/Users/gabadi/workspace/gabadi/saga-umf-integration/features/parallel-workers.feature","background_hash":"1dd133df71819ac82cc0542649edb76c526b89f2510b6d55591dcaf624a517b7","implementation_hash":"unknown","scenarios":[{"index":0,"name":"the worker count and site count decide serial vs parallel","scenario_hash":"6ff2b3e6952131c00ca83cd12417037ee749900fb41eb6207a7a4ad53a1c8fd4","mutation_count":20,"result":{"Total":20,"Killed":20,"Survived":0,"Errors":0},"tested_at":"2026-10-11T07:48:07Z"},{"index":1,"name":"the worker count clamps to the number of selected sites","scenario_hash":"f5eda1c453ac6638be97aca58c1052714aadee7a441a652d024f409de7864aa8","mutation_count":8,"result":{"Total":8,"Killed":8,"Survived":0,"Errors":0},"tested_at":"2026-10-11T07:48:07Z"},{"index":2,"name":"the workers header line prints whenever --max-workers is set","scenario_hash":"edc704f1fb39eb9f65c4eb5ae9e52a5e7927c552fad75296b38e05844da0b869","mutation_count":16,"result":{"Total":16,"Killed":16,"Survived":0,"Errors":0},"tested_at":"2026-10-11T07:48:07Z"},{"index":3,"name":"the per-mutant worker token appears only on the parallel path","scenario_hash":"be39e64f6588e08da20a168912a1c70759e23d8f2ea83995eee46a24326dc027","mutation_count":15,"result":{"Total":15,"Killed":15,"Survived":0,"Errors":0},"tested_at":"2026-10-11T07:48:07Z"},{"index":5,"name":"a parallel mutant is classified exactly as the serial path would","scenario_hash":"5c69fed5050741213961f704d540a015795e03bb7ac1d8243a3b0755f603b6dc","mutation_count":9,"result":{"Total":9,"Killed":9,"Survived":0,"Errors":0},"tested_at":"2026-10-11T07:48:07Z"},{"index":8,"name":"the worker tree copy handles skip-list and regular entries without error","scenario_hash":"f4747d6f69f376da07197fc5af72dd02bc6b7a27bc78238f46e45af377793040","mutation_count":4,"result":{"Total":4,"Killed":4,"Survived":0,"Errors":0},"tested_at":"2026-10-11T07:48:07Z"},{"index":10,"name":"a worker error or short result count aborts strictly","scenario_hash":"2826b57cd33e77f7f65e66d3ec7518347ab755599e4bf531aed690dfaabe1220","mutation_count":4,"result":{"Total":4,"Killed":4,"Survived":0,"Errors":0},"tested_at":"2026-10-11T07:48:07Z"}]}
# acceptance-mutation-manifest-end

Feature: Parallel worker execution for --max-workers

  # TRACKING: F6 (parallel-workers) — CONTEXT.md "Parallel workers (F6)";
  #           docs/adr/0015-parallel-workers-via-uv-clone-per-worker.md (mechanism +
  #           grilling resolutions 1-9).
  #           Upstream ground truth: unclebob/mutate4go internal/runner/runner.go
  #           (runMutations switch :319, runMutationsParallel :351, copyProject :487,
  #           shouldSkipCopy :527, sortResults :457, printHeader :614, per-mutant :425).
  #
  # CONTRACT:
  #   command: mutate4py <file> --max-workers <n> <coverage flag> [--pytest-args ARGS]
  #            [selection flags] [--timeout-factor N] [--mutation-warning N]
  #   request:
  #     <file> — path, required; a Python source file with selected mutation sites (F1).
  #     --max-workers <n> — non-negative int, already parsed+validated by F5; F6 consumes it.
  #     all other flags — parsed by F5, behave exactly as F4 (coverage, selection, timeout).
  #   path selection (the switch, upstream runner.go:319):
  #     --max-workers <= 1 OR selected sites <= 1 -> SERIAL path (the unchanged F4 loop).
  #     --max-workers >= 2 AND selected sites >= 2 -> PARALLEL path (the F6 engine).
  #   stdout — identical to the F4 run output, with two additions governed by flag/path:
  #     Mutation workers: <n>   — printed whenever --max-workers > 0 (serial OR parallel);
  #                               <n> is the clamped count on the parallel path.
  #     [i/total] worker-<k> <status> line <L> <desc>: <functionID>
  #                             — per-mutant line ONLY on the parallel path; carries the
  #                               worker-<k> token. <i> is the stable site index.
  #   response (worker failure, non-zero exit, parallel path): no "Mutation Report";
  #     either "mutation worker failed: <reason>" (a worker could not write/restore its
  #     copy) or "mutation workers stopped after <k>/<n> results" (collected != selected).
  #   response (target outside cwd, parallel path): a hard error, non-zero exit, before
  #     any worker is provisioned; no worker tree created.
  #   NOT in the response: on any SERIAL run, no "worker-<k>" token (even when the
  #     "Mutation workers:" line prints); no per-worker ".mutate4py.bak".
  #
  # CONSTRAINTS:
  #   - The switch is exactly upstream's: serial unless (--max-workers >= 2 AND >= 2
  #     selected sites). --max-workers 0/1, or a clamp-to-one-site run, is serial.
  #   - maxWorkers is clamped to the selected-site count; the "Mutation workers:" line
  #     shows the clamped count (upstream runner.go:368).
  #   - The "Mutation workers:" line tracks the FLAG (--max-workers > 0), not the path
  #     (upstream runner.go:614). The "worker-<k>" token tracks the PATH (parallel only).
  #   - Each worker is a tree copy of the working dir under
  #     .mutate4py/workers/run-<pid>-<nanos>/worker-<k>/, with its own uv-provisioned
  #     venv; it runs pytest with the run's --pytest-args verbatim, no shell,
  #     with cwd = worker-root. No
  #     "uv pip install -e", no "uv run" wrapping (ADR 0015 resolution 1).
  #   - The copy skips .git, __pycache__, .venv, .pytest_cache, .mypy_cache,
  #     .ruff_cache, and the .mutate4py/ worker dir itself (ADR 0015 resolution 3).
  #   - Classification (killed / survived / timeout) is identical to the serial path for
  #     the same mutant; only isolation and the worker-<k> token differ.
  #   - Per-mutant lines print in arrival order (workers finish out of sequence); the
  #     Mutation Report tallies and Survivors: block are sorted by stable site index and
  #     are therefore deterministic (upstream sortResults runner.go:457).
  #   - Worker failure is strict / all-or-nothing: any worker write/restore error, or a
  #     collected-result count != selected-site count, aborts the run with no report.
  #   - The whole run-<pid>-<nanos> worker root is removed when the run ends, on success
  #     and on failure (upstream defer os.RemoveAll runner.go:371).
  #
  # SEQUENCING:
  #   - The serial/parallel switch is decided AFTER site selection (the switch reads the
  #     selected-site count), BEFORE the baseline timeout drives the per-mutant runs.
  #   - On the parallel path, every worker copy is provisioned BEFORE any mutant runs.
  #   - The target-outside-cwd hard error fires BEFORE any worker is provisioned.
  #   - .mutate4py.bak is saved on the original and the manifest re-embedded on the
  #     original AFTER aggregation — unchanged from F4 (the parallel engine slots inside
  #     runMutations between save-backup and restore-source).
  #
  # NFR:
  #   - Worker provisioning uses uv (near-instant venv + hardlinked installs) so N
  #     copies are cheap; this is the cost lever that makes clone-per-worker practical.
  #   - A worker failure exits non-zero so CI fails loudly; no partial/misleading report.
  #   - Each per-mutant test run is bounded by the same mutant timeout as serial so one
  #     hung worker mutant cannot stall the run.
  #
  # SIDE EFFECTS:
  #   - On the parallel path the run creates and then removes
  #     .mutate4py/workers/run-<pid>-<nanos>/; the only persistent change to <file> is
  #     the re-embedded manifest footer (same as F4). In parallel the original file is
  #     never mutated — only worker copies are — so .mutate4py.bak is pure crash-safety.
  #   - The acceptance entrypoint generator and step handlers must learn parallel steps:
  #     run with --max-workers N over a multi-site file; assert the Mutation workers line;
  #     assert each per-mutant line carries a worker-<k> token; assert the worker root is
  #     created during and absent after the run; script a worker write/restore failure.
  #
  # SCOPE:
  #   - Does NOT: parse or validate --max-workers (F5); it consumes the parsed count.
  #   - Does NOT: change the serial run loop (F4); the serial path is byte-identical to
  #     F4 except for the conditional "Mutation workers:" header line.
  #   - Does NOT: re-implement site discovery (F1), manifest (F2), the LCOV gate (F3),
  #     the report format (F4), or the splice/restore primitive (F1, reused per worker).
  #   - Does NOT: parallelize across files — only across the selected sites of the one
  #     target file (upstream mutates one file per invocation).
  #   - ASSUMED: uv is available on PATH in the run environment; the exact provisioning
  #     commands (uv venv / uv sync) and subprocess mechanism are the coder's to pin.
  #   - ASSUMED: the injected exec seam runs pytest (no shell) in a given working directory
  #     and reports exit status / timeout (same seam F4 assumes), now per worker copy.
  #
  # UX INTENT: none
  # Design artifacts: none

  Background:
    Given a Python source file with covered mutation sites
    And a baseline test command that passes

  # parallel-workers-1: the serial/parallel switch follows --max-workers and site count.
  # The effective-0 serial path is reachable ONLY by omitting the flag (the default);
  # --max-workers 0 is a usage error (positive-int flag, see cli-surface-2), so the
  # "0 workers -> serial" case is exercised via the unset default, not a literal 0.
  Scenario Outline: the worker count and site count decide serial vs parallel
    Given the file has "<sites>" selected mutation sites
    And the max-workers flag is "<flag>"
    When I run mutate4py mutating that file
    Then the run takes the "<path>" path
    And the output line "Total mutation sites: <total>" is printed

    # <sites> drives the fixture size; <total> is the count the run must report.
    # They match but are separate columns, so mutating either literal — or the
    # <flag> string (a garbage flag aborts before the header prints) — is caught.
    Examples:
      | flag            | sites | total | path     |
      | (unset)         | 5     | 5     | serial   |
      | --max-workers 1 | 5     | 5     | serial   |
      | --max-workers 4 | 1     | 1     | serial   |
      | --max-workers 2 | 2     | 2     | parallel |
      | --max-workers 4 | 5     | 5     | parallel |

  # parallel-workers-2: maxWorkers is clamped to the selected-site count
  # Clamp-DOWN correctness (workers > sites -> shown == sites) is verified by the unit test
  # test_parallel_path_workers_header_clamped. The above-clamp regime is an equivalent-mutant
  # trap for gherkin: mutating the workers cell upward (e.g. 8 -> 17) still clamps to the same
  # site count, so no row here would catch it. This scenario therefore covers only the
  # load-bearing regime (workers <= sites, plus the equal boundary) where shown == workers.
  Scenario Outline: the worker count clamps to the number of selected sites
    Given the file has "<sites>" selected mutation sites
    And the flag supplied is "--max-workers <workers>"
    When I run mutate4py mutating that file
    Then the output line "Mutation workers: <shown>" is printed
    And the output line "Total mutation sites: <total>" is printed

    # <sites> drives the fixture; <total> is the reported count and <shown> the
    # clamped worker count — separate columns so mutating any input literal is caught.
    Examples:
      | workers | sites | total | shown |
      | 4       | 5     | 5     | 4     |
      | 2       | 2     | 2     | 2     |

  # parallel-workers-3: the Mutation workers line tracks the flag, not the path.
  # The header is suppressed only when the flag is unset (default serial); a literal
  # --max-workers 0 is a usage error (see cli-surface-2), so the "is not" case is
  # exercised via the unset default rather than a literal 0.
  Scenario Outline: the workers header line prints whenever --max-workers is set
    Given the file has "<sites>" selected mutation sites
    And the max-workers flag is "<flag>"
    When I run mutate4py mutating that file
    Then a "Mutation workers:" line "<visibility>" printed
    And the output line "Total mutation sites: <total>" is printed

    # <sites> drives the fixture; <total> is the reported count — separate columns so
    # mutating either literal, or the <flag> string (garbage aborts before the
    # header prints), is caught.
    Examples:
      | flag            | sites | total | visibility |
      | (unset)         | 5     | 5     | is not     |
      | --max-workers 1 | 5     | 5     | is         |
      | --max-workers 4 | 1     | 1     | is         |
      | --max-workers 4 | 5     | 5     | is         |

  # parallel-workers-4: the worker-<k> token tracks the path, not the flag
  Scenario Outline: the per-mutant worker token appears only on the parallel path
    Given the file has "<sites>" selected mutation sites
    And the flag supplied is "--max-workers <workers>"
    When I run mutate4py mutating that file
    Then a "worker-" token "<visibility>" present in every per-mutant progress line
    And the output line "Total mutation sites: <total>" is printed
    And the output line "Mutation workers: <shown>" is printed

    # <sites> drives the fixture; <total> is the reported count and <shown> the
    # displayed worker count (clamped on the parallel path) — separate columns so
    # mutating any input literal is caught.
    Examples:
      | workers | sites | total | shown | visibility |
      | 1       | 5     | 5     | 1     | is not     |
      | 4       | 1     | 1     | 4     | is not     |
      | 4       | 5     | 5     | 4     | is         |

  # parallel-workers-5: the parallel per-mutant line is the verbatim upstream format
  Scenario: a parallel per-mutant line carries the worker token in upstream format
    Given the file has "4" selected mutation sites
    And a selected site with index "2" on line 7 in function "func/calc" mutating "a > b" to "a >= b"
    And that mutant is run by worker "3" and exits nonzero
    And the flag supplied is "--max-workers 4"
    When I run mutate4py mutating that file
    Then the output line "[2/4] worker-3 killed line 7 a > b -> a >= b: func/calc" is printed

  # parallel-workers-6: parallel classification matches serial for the same mutant
  Scenario Outline: a parallel mutant is classified exactly as the serial path would
    Given a selected site whose mutated test run will "<outcome>"
    And the flag supplied is "--max-workers 4"
    And the file has "4" selected mutation sites
    When I run mutate4py mutating that file
    Then the progress line for that mutant shows status "<status>"
    And the report counts that mutant as "<tally>"

    Examples:
      | outcome        | status   | tally    |
      | exit nonzero   | killed   | Killed   |
      | exceed timeout | timeout  | Killed   |
      | exit zero      | survived | Survived |

  # parallel-workers-7: per-mutant lines print in arrival order, the report is index-sorted
  Scenario: progress prints in arrival order but the report is deterministic
    Given the file has "3" selected mutation sites at indexes "1", "2", "3"
    And the workers finish the mutants in order "3", "1", "2"
    And the flag supplied is "--max-workers 3"
    When I run mutate4py mutating that file
    Then the per-mutant lines appear in arrival order "3", "1", "2"
    And the "Survivors:" block lists sites sorted by stable index
    And the "Mutation Report" tallies are independent of finish order

  # parallel-workers-8: each worker mutates and restores only its own copy
  Scenario: a worker mutates its own copy and the original file is never spliced
    Given the file has "4" selected mutation sites
    And the flag supplied is "--max-workers 4"
    When I run mutate4py mutating that file
    Then each worker has its own copy under ".mutate4py/workers/"
    And each worker copy is restored to the original after its mutant
    And the original source file is never spliced with a mutant during the run
    And no per-worker ".mutate4py.bak" file is created

  # parallel-workers-9: the worker copy skips VCS, caches, and the worker dir itself
  # Skip-list correctness (presence/absence in worker copies) is verified by unit tests for _copy_tree.
  # This scenario verifies that the parallel run completes successfully when these entries exist in the cwd.
  Scenario Outline: the worker tree copy handles skip-list and regular entries without error
    Given the working directory contains a "<entry>" entry
    And the flag supplied is "--max-workers 4"
    And the file has "4" selected mutation sites
    When I run mutate4py mutating that file
    Then the run completes successfully

    Examples:
      | entry       |
      | .git        |
      | __pycache__ |
      | .mutate4py  |
      | src         |

  # parallel-workers-10: the worker root is created during and removed after the run
  Scenario: the worker run root is cleaned up when the run ends
    Given the file has "4" selected mutation sites
    And the flag supplied is "--max-workers 4"
    When I run mutate4py mutating that file
    Then a worker run root existed under ".mutate4py/workers/" during the run
    And no worker run root remains under ".mutate4py/workers/" after the run

  # parallel-workers-11: a worker failure aborts the whole run with no report
  Scenario Outline: a worker error or short result count aborts strictly
    Given the file has "4" selected mutation sites
    And the flag supplied is "--max-workers 4"
    And "<failure>" occurs during the parallel run
    When I run mutate4py mutating that file
    Then the command exits with a non-zero status
    And the output contains "<message>"
    And no "Mutation Report" is printed

    Examples:
      | failure                              | message                          |
      | a worker cannot write its file copy  | mutation worker failed           |
      | a worker stops before all sites run  | mutation workers stopped after   |

  # parallel-workers-12: a target outside the working directory is a hard error
  Scenario: a target file outside the working directory is rejected before provisioning
    Given the target file is outside the working directory
    And the flag supplied is "--max-workers 4"
    And the file has "4" selected mutation sites
    When I run mutate4py mutating that file
    Then the command exits with a non-zero status
    And the output contains "must be inside working directory"
    And no worker root is created under ".mutate4py/workers/"

  # parallel-workers-13: the manifest is re-embedded once on the original after aggregation
  Scenario: the parallel run re-embeds a fresh manifest on the original file
    Given the file has "4" selected mutation sites
    And the flag supplied is "--max-workers 4"
    When I run mutate4py mutating that file
    Then after the run the original source has no mutant spliced in
    And the original source ends with a fresh "mutate4py-manifest" footer
    And no ".mutate4py.bak" file is left behind

  # parallel-workers-14: a src-layout editable project kills every mutant under parallel workers
  # Regression for ADR 0015: the worker venv must import the worker copy's src,
  # so each mutant is killed by its own worker rather than surviving against the original.
  Scenario: a src-layout editable project kills every mutant under parallel workers
    Given the project is a src-layout editable package with pytest and pytest-cov
    And the flag supplied is "--max-workers 2"
    When I run mutate4py mutating that file
    Then the run takes the "parallel" path
    And the output contains "Killed: 2"
    And the output contains "Survived: 0"
    And the run completes successfully
    And the same file run without --max-workers reports the same Killed and Survived counts

  # parallel-workers-15: a worker venv without pytest-cov runs without a --no-cov usage abort
  # The orchestrator has pytest-cov; the worker venv does not. Plugin neutralisation is
  # computed by the worker's own interpreter, so no --no-cov reaches the worker pytest.
  Scenario: a worker venv without pytest-cov runs its mutants without a usage error
    Given the project is a src-layout editable package with pytest but without pytest-cov
    And the flag supplied is "--max-workers 2"
    When I run mutate4py mutating that file
    Then the run takes the "parallel" path
    And the output does not contain "unrecognized arguments"
    And the output contains "Killed: 2"
    And the run completes successfully
