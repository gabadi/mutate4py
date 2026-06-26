# acceptance-mutation-manifest-begin
# {"version":1,"tested_at":"2026-06-26T05:40:35.931343Z","feature_name":"Mutation site discovery and the --scan count surface","feature_path":"features/site-discovery.feature","background_hash":"74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b","implementation_hash":"sha256:7d11c2780158ee167578924c3fe438ab5232fb807625a999b4a362e76ed04fdf","scenarios":[]}
# acceptance-mutation-manifest-end

Feature: Mutation site discovery and the --scan count surface

  # TRACKING: F1 (site-discovery) — docs/plan.md; docs/spec.md §3, §4, §8 (--scan);
  #           docs/adr/0001-site-discovery-and-operators.md;
  #           docs/adr/0002-scan-counts-only-no-manifest-in-f1.md
  #
  # CONTRACT:
  #   command: mutate4py <file> --scan
  #   request: <file> — path to a Python source file (positional, required)
  #            --scan — flag selecting read-only count mode
  #   stdout (exit 0), exactly this block:
  #     Mutation scan: <file>
  #     Total mutation sites: <n>
  #     Changed mutation sites: <n>
  #     Manifest exists: <true|false>
  #   plus, when <n> exceeds the warning threshold:
  #     Warning: <n> mutation sites exceeds threshold <m>.
  #   response (usage error, non-zero exit): <file> missing/unreadable → usage error on stderr.
  #   NOT in the response: no per-site listing, no coverage %, no test results,
  #     no survivors/killed counts (those are the F4 run report).
  #
  # CONSTRAINTS:
  #   - One file at a time (positional <file>).
  #   - Exactly one mutant per site; one operator/literal per site.
  #   - Operator catalogue is closed (spec §3): + - *, > >= < <=, == !=, is/is not,
  #     in/not in, and/or, True/False, integer 0/1. `*`→`/` only (never `/`→`*`).
  #   - Excluded — NO site emitted: augmented assignment (+=, -=), unary removal,
  #     any cross-coercion-family swap, integer literals other than 0 and 1.
  #   - A site outside any function has an empty FunctionID and is still counted.
  #   - Nested def / lambda sites fold into the enclosing named unit (not separate units).
  #   - In F1 there is no manifest code: Manifest exists is always false, and
  #     Changed always equals Total.
  #   - --scan is read-only: no coverage acquired, no test command run, no file write.
  #
  # SEQUENCING: none
  #
  # NFR:
  #   - Deterministic: re-running --scan on identical source yields an identical block.
  #   - Sites are ordered by (line, column) with a stable Index.
  #
  # SIDE EFFECTS: none
  #   # --scan writes nothing; it does not embed or modify the manifest.
  #
  # SCOPE:
  #   - Does NOT: acquire or read coverage (F3); --scan never touches coverage.
  #   - Does NOT: run tests, classify mutants, or print a run report (F4).
  #   - Does NOT: read, diff, or write the manifest (F2) — Manifest exists is always
  #     false here and Changed == Total.
  #   - Does NOT: implement the full flag matrix or mutual-exclusion rules (F5);
  #     only <file>, --scan, --help exist in F1.
  #   - Does NOT: list per-site descriptions under --scan (counts only; ADR 0002).
  #   - ASSUMED: per-operator and per-attribution correctness is also covered by the
  #     discovery module's unit tests; the Gherkin asserts the count contract.
  #
  # UX INTENT: none
  # Design artifacts: none

  # site-discovery-1: every catalogued operator/literal is exactly one site
  Scenario Outline: a catalogued construct yields one mutation site
    Given a Python file whose only mutable construct is "<construct>"
    When the file is scanned
    Then the total mutation sites is <count>

    Examples:
      | construct  | count |
      | a + b      | 1     |
      | a - b      | 1     |
      | a * b      | 1     |
      | a > b      | 1     |
      | a >= b     | 1     |
      | a < b      | 1     |
      | a <= b     | 1     |
      | a == b     | 1     |
      | a != b     | 1     |
      | a is b     | 1     |
      | a is not b | 1     |
      | a in b     | 1     |
      | a not in b | 1     |
      | a and b    | 1     |
      | a or b     | 1     |
      | True       | 1     |
      | False      | 1     |
      | 0          | 1     |
      | 1          | 1     |

  # site-discovery-2: excluded constructs emit no site
  Scenario Outline: an excluded construct yields no mutation site
    Given a Python file whose only candidate construct is "<construct>"
    When the file is scanned
    Then the total mutation sites is 0

    Examples:
      | construct |
      | a += b    |
      | a -= b    |
      | a / b     |
      | -a        |
      | 2         |

  # site-discovery-3: a site is attributed to its enclosing function unit
  Scenario Outline: a site inside a function is attributed to that unit
    Given a Python file defining "<definition>" containing one mutable site
    When the file is scanned
    Then the site's function id is "<function_id>"

    Examples:
      | definition                     | function_id |
      | def foo                        | func/foo    |
      | async def foo                  | func/foo    |
      | class C with method m          | func/C.m    |
      | module-level code (no def)     |             |
      | def outer with a nested def    | func/outer  |
      | def outer with a lambda        | func/outer  |

  # site-discovery-4: --scan prints the count block, read-only, no manifest in F1
  Scenario Outline: scanning a file prints the count block with no manifest
    Given a Python file containing <total> mutation sites and no embedded manifest
    When the command "mutate4py <file> --scan" is run
    Then the output line "Total mutation sites: <total>" is printed
    And the output line "Changed mutation sites: <total>" is printed
    And the output line "Manifest exists: false" is printed
    And no test command is run
    And the file is left unchanged

    Examples:
      | total |
      | 0     |
      | 1     |
      | 7     |

  # site-discovery-5: the warning line appears only when sites exceed the threshold
  Scenario Outline: the warning line is gated by the threshold
    Given a Python file containing <total> mutation sites
    And the mutation warning threshold is <threshold>
    When the file is scanned
    Then the warning line is "<warning>"

    Examples:
      | total | threshold | warning                                            |
      | 50    | 50        |                                                    |
      | 51    | 50        | Warning: 51 mutation sites exceeds threshold 50.   |
      | 3     | 2         | Warning: 3 mutation sites exceeds threshold 2.     |

  # site-discovery-6: a missing source file is a usage error
  Scenario: scanning a missing file is a usage error
    Given the path "<missing>" does not exist
    When the command "mutate4py <missing> --scan" is run
    Then the command exits with a usage error
    And no mutation scan block is printed
