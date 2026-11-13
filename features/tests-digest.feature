Feature: A scored function stays proven while the tests that reach it do not change

  # TRACKING: Issue #88 (acceptance criteria); Issue #106 (skip rule, recorded Survivors)
  #           docs/adr/0029-per-function-tests-digest-and-skip-rule.md (digest inputs,
  #           Site-lines-only, skip rule, adoption, accepted gaps); docs/adr/0022 (the
  #           counter-examples a narrow input set got wrong); docs/adr/0026
  #           (Survivors fail the run).
  #
  # CONTRACT:
  #   command: mutate4py <file-or-dir> --pytest-args <args> [--allow-survivors]
  #   skip rule — a function is re-scored when it is unscored, its Unit hash changed,
  #     its fresh tests digest differs from the stored one, an Accepted equivalent lost
  #     its marker, or it has Survivors and no stored digest (a 0.2.x entry). A function
  #     whose hash and digest are both unchanged is skipped, even with Survivors.
  #   report — the progress lines name every function a run re-scored. The Survivors a
  #     skipped function kept from the Manifest print on their own
  #     "Recorded survivors (function unchanged, not re-run):" block, apart from this run's "Survivors:".
  #   exit code — recorded Survivors count like this run's: exit 3, or 0 with
  #     --allow-survivors.
  #   --check-manifest — checks hashes, recorded Survivors and equivalent markers. It
  #     never computes a digest, so a stale digest does not fail it.
  #
  # CONSTRAINTS:
  #   - A function's digest reads the test files that reach its covered Site lines, the
  #     conftests above them and the support files under a test root. A line that only
  #     defines the function (def, decorator) is not a Site line.
  #   - A support file under a test root (a factory, a helper in a sibling directory)
  #     is a run-level input: it sits in every function's digest, because the digest
  #     cannot tell which test imports it without guessing from directory shape
  #     (ADR 0022). An edit to one re-scores every scored function.
  #   - A helper outside every test root is not a digest input (ADR 0029, accepted gap).
  #   - An entry without a stored digest and without Survivors adopts the fresh digest
  #     with no re-score.

  # ── #88 AC: an edit to a test re-scores only what that test reaches ─────────────

  Scenario: an edit to a test that loads a module re-scores only that module's functions
    Given a project of five modules, each with its own tests, scored once
    When the file "tests/pkg_a/test_alpha.py" is edited without changing what it does
    And mutate4py is run again
    Then the functions re-scored are func/inc, func/dec

  Scenario: an edit to an unrelated test re-scores nothing
    Given a project of five modules, each with its own tests, scored once
    When the file "tests/test_other.py" is edited without changing what it does
    And mutate4py is run again
    Then no function is re-scored

  # ── #88 AC: each ADR 0022 counter-example invalidates the proofs it affects ─────

  Scenario: an edit to a conftest above a covering test re-scores that test's functions
    Given a project of five modules, each with its own tests, scored once
    When the file "tests/pkg_a/conftest.py" is edited without changing what it does
    And mutate4py is run again
    Then the functions re-scored are func/inc, func/dec

  Scenario: an edit to a factory module under the tests directory re-scores every function
    Given a project of five modules, each with its own tests, scored once
    When the file "tests/factories.py" is edited without changing what it does
    And mutate4py is run again
    Then every function is re-scored

  Scenario: an edit to a helper in a sibling directory of the test re-scores every function
    Given a project of five modules, each with its own tests, scored once
    When the file "tests/helpers/builders.py" is edited without changing what it does
    And mutate4py is run again
    Then every function is re-scored

  # ── what the digest must not read ───────────────────────────────────────────────

  Scenario: an edit to a helper outside every test root re-scores nothing
    Given a project of five modules, each with its own tests, scored once
    When the file "tools/stamp.py" is edited without changing what it does
    And mutate4py is run again
    Then no function is re-scored

  Scenario: an edit to a test that only reaches the definition line re-scores nothing
    Given a project of five modules, each with its own tests, scored once
    When the file "tests/test_delta_a_load.py" is edited without changing what it does
    And mutate4py is run again
    Then no function is re-scored

  Scenario: an edit to the test that calls the function re-scores it
    Given a project of five modules, each with its own tests, scored once
    When the file "tests/test_delta_b_call.py" is edited without changing what it does
    And mutate4py is run again
    Then the functions re-scored are func/twice

  # ── the skip rule: a function with Survivors is skipped while nothing it reads moved ──

  Scenario: a function with Survivors whose tests did not change is skipped and its Survivors are recorded
    Given a module whose two functions survive their tests, scored once
    When mutate4py is run again
    Then no function is re-scored
    And the recorded Survivors block names "func/keep" and "func/other"
    And the exit code is 3

  Scenario: recorded Survivors print apart from this run's Survivors
    Given a module whose two functions survive their tests, scored once
    When the body of "other" in "sur.py" is changed
    And mutate4py is run again
    Then the functions re-scored are func/other
    And the Survivors block names only "func/other"
    And the recorded Survivors block names only "func/keep"
    And the exit code is 3

  Scenario: --allow-survivors turns the recorded Survivors into exit 0
    Given a module whose two functions survive their tests, scored once
    When mutate4py is run again with "--allow-survivors"
    Then no function is re-scored
    And the recorded Survivors block names "func/keep" and "func/other"
    And the exit code is 0

  # ── adoption: a 0.2.x entry with Survivors is re-scored once, then skipped ──────

  Scenario: a 0.2.x entry with Survivors is re-scored once and then skipped
    Given a module whose two functions survive their tests, scored once
    And the Manifest is stored as a 0.2.x run left it, with no tests digests
    When mutate4py is run again
    Then the functions re-scored are func/keep, func/other
    And there is no recorded Survivors block
    When mutate4py is run again
    Then no function is re-scored
    And the recorded Survivors block names "func/keep" and "func/other"

  # ── --check-manifest does not read digests ──────────────────────────────────────

  Scenario: --check-manifest states and keeps to what it checks
    Given a project of five modules, each with its own tests, scored once
    When mutate4py is run with "--help"
    Then the "--check-manifest" help states it checks hashes, Survivors and markers, not tests digests

  Scenario: --check-manifest passes while a test the digest reads has changed
    Given a project of five modules, each with its own tests, scored once
    When the file "tests/test_beta.py" is edited without changing what it does
    And mutate4py is run again with "--check-manifest"
    Then the exit code is 0
