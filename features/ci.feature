Feature: Continuous integration and release pipeline

  # TRACKING: F1 (site-discovery) — user directive: F1 includes CI + releasable skeleton;
  #           base ~/workspace/addi/crap4py .github/workflows
  #
  # CONTRACT:
  #   trigger: push to branch main; pull_request.
  #   ci gates run in sequence on a single ubuntu-latest job, fresh uv runtime:
  #     1. lint — ruff check src/ tests/
  #     2. format — ruff format --check src/ tests/
  #     3. test — pytest --cov (emits lcov.info), fails under the coverage floor
  #     4. dry — drywall src/
  #   conclusion: success iff every gate passes; failure iff any gate fails; the
  #     failed step is identifiable.
  #   release trigger: a pushed tag matching v*.*.*; steps: uv build → publish to
  #     PyPI → create GitHub release.
  #
  # CONSTRAINTS:
  #   - Single environment: one ubuntu-latest runner, one pinned Python (no matrix).
  #   - Gates run in the fixed order above; a failed gate stops the run.
  #   - CRAP and mutation gates are deferred — a commented placeholder only — until
  #     the runner (F4) and a first implementation land.
  #   - No build gate in CI (pure-Python, runs directly); build happens only on release.
  #
  # SEQUENCING:
  #   - The lint/format/test/dry gates each require checkout + uv setup first.
  #   - release: uv build must complete before publish to PyPI.
  #
  # NFR:
  #   - The trunk is verified on every push to main, not only on pull requests.
  #
  # SIDE EFFECTS:
  #   - Adds .github/workflows/ci.yml and .github/workflows/release.yml.
  #   - The DRY gate requires the drywall release binary available on the runner.
  #   - Extends .gitignore with Python build/test/coverage artifacts and .mutate4py.bak.
  #
  # SCOPE:
  #   - Does NOT: run CRAP or mutation gates yet (deferred — placeholder).
  #   - Does NOT: run a multi-OS or multi-Python-version matrix.
  #   - Does NOT: build in the CI job (only in release).
  #   - ASSUMED: the drywall binary is fetched onto the runner before the DRY gate;
  #     PyPI publishing uses a trusted-publisher / pypi environment as in crap4py.
  #
  # UX INTENT: none
  # Design artifacts: none

  # ci-1: an all-green change passes CI
  Scenario Outline: an all-green change passes CI
    Given a <ref_kind> against main
    And every CI gate would pass
    When CI runs
    Then the CI conclusion is "success"

    Examples:
      | ref_kind     |
      | pull request |
      | push to main |

  # ci-2: any single failing gate fails the run and names the gate
  Scenario Outline: a single failing gate fails CI
    Given a pull request against main
    And the "<gate>" gate would fail
    When CI runs
    Then the CI conclusion is "failure"
    And the failed step is "<gate>"

    Examples:
      | gate   |
      | lint   |
      | format |
      | test   |
      | dry    |

  # ci-3: CRAP and mutation gates are deferred, not active
  Scenario Outline: a deferred gate does not run in F1
    Given the CI workflow for F1
    When CI runs
    Then the "<deferred_gate>" gate does not execute

    Examples:
      | deferred_gate |
      | crap          |
      | mutation      |

  # ci-4: a release tag builds and publishes
  Scenario: a version tag triggers build and publish
    Given a pushed tag "<tag>" matching v*.*.*
    When the release workflow runs
    Then the package is built with "uv build"
    And the package is published to PyPI
    And a GitHub release is created
