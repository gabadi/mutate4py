Feature: Per-mutant test selection and directory run mode

  # TRACKING: Issue #15 — directory run mode
  #           Issue #27 — per-mutant selection, no silent full-suite fallback
  #           docs/adr/0027-single-session-ctrace-measurement-unit-only-scoring.md
  #           (the Measurement and its Test map); docs/adr/0018 (the selection
  #           rules and the no-tests hint); CONTEXT.md "Test selection".
  #
  # CONTRACT:
  #   command: mutate4py <file-or-dir> [other flags]
  #   --test-contexts and --build-test-contexts are removed: every run measures
  #     coverage itself, so there is no db to point at.
  #   directory run mode — when <file-or-dir> is a directory, iterate over
  #     all .py files and run mutations on each; exit non-zero if any file
  #     has survivors or errors.
  #   per-mutant selection — the run's Measurement names, for each line, the
  #     tests that reached it (the Test map). Every selected site's line has
  #     exactly one Selection outcome:
  #       narrowed  — named tests reached the line: run only those.
  #       static    — only the Empty context reached it (import-time code no
  #                   single test owns): run the full --pytest-args verbatim.
  #       uncovered — no context reached it: the site is not mutated by
  #                   default; under --mutate-all it runs the full --pytest-args
  #                   and is tallied as static.
  #   report line — the Mutation Report prints "Test selection: narrowed <n>,
  #     static <k>" after the "Uncovered:" line and before any "Survivors:" block.
  #   survivors — each Survivor is confirmed by re-running the full test set,
  #     pytest-args verbatim, never narrowed.
  #   no tests — a Measurement whose session collects no tests stops the run
  #     with exit 1 and the no-tests hint (pytest exit 5).
  #   parallelism — --max-workers >= 2 composes: each Worker's dispatch is
  #     narrowed or static per mutant, the same as the serial loop's.
  #
  # CONSTRAINTS:
  #   - Narrowed argv: the run's pytest_args with the positional path removed,
  #     then the node IDs (no shell, no quoting — a plain argument list).
  #   - Static argv and confirmation argv: pytest_args verbatim.
  #   - Directory run mode: skips __pycache__ directories.
  #   - Directory run mode: files processed in sorted order; per-file run is serial.
  #   - Directory run mode: exits non-zero if ANY file's run exits non-zero.
  #
  # SEQUENCING:
  #   - The Measurement runs before any Mutant is spliced into a source file.

  Scenario: directory run mode iterates over all .py files
    Given a directory "src/" containing two Python files "a.py" and "b.py"
    When mutate4py is run on the directory in scan mode
    Then the output contains two "Mutation scan:" lines

  Scenario: directory run mode exits non-zero if any file fails
    Given a directory "src/" containing Python files
    When mutate4py is run on the directory in run mode and one file fails to parse
    Then the exit code is non-zero

  # narrowed — named tests reached the line, so only those run
  Scenario: a line reached by named tests runs only those tests
    Given a Python source file with covered mutation sites
    When mutate4py is run without extra flags
    Then that mutant's test command is "pytest test_dummy.py::test_dummy"
    And the report line "Test selection: narrowed 1, static 0" is printed
    And the "Test selection:" line follows "Uncovered:" and precedes "Survivors:"

  # static — import-time code: no test owns the line, so the full set runs
  Scenario: a line executed only at import time runs the full test command
    Given a Python source file whose only sites run at import time
    When mutate4py is run without extra flags
    Then that mutant's test command is the full "--pytest-args" verbatim
    And the report line "Test selection: narrowed 0, static 2" is printed

  # uncovered — nothing reached the line, so the default run mutates nothing there
  Scenario: a line no test reached is not mutated by default
    Given a Python source file that no test reaches
    When mutate4py is run without extra flags
    Then the report line "Uncovered: 1" is printed
    And the report line "Test selection: narrowed 0, static 0" is printed

  # a Survivor of a narrowed Mutant is re-run on the full test set
  Scenario: a Survivor is confirmed on the full test set
    Given a Python source file with covered mutation sites
    When mutate4py is run without extra flags
    Then that mutant's test command is "pytest test_dummy.py::test_dummy"
    And the survivor's confirmation run is the full "--pytest-args" verbatim

  # no tests — the Measurement collected nothing, so the run has no Baseline
  Scenario: a suite that collects no tests stops the run with the no-tests hint
    Given a Python source file with no tests
    When mutate4py is run without extra flags
    Then the exit code is 1
    And the output contains "the Measurement collected no tests"
    And the output contains "pytest collected no tests to run (exit 5)"

  Scenario: --max-workers 4 composes with the per-mutant selection
    Given a Python source file with mutation sites covered by known tests
    When mutate4py is run with "--max-workers 4"
    Then worker-N tokens are present in the progress lines
    And the report line "Test selection: narrowed 2, static 0" is printed
