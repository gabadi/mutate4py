# mutation-stamp: sha256=afff7cbff1ec7730c7385b1326034479ca3f9216aa7e8dcfd2aed1094eea211a
# acceptance-mutation-manifest-begin
# {"version":1,"tested_at":"2026-07-02T14:16:59.215041Z","feature_name":"Manifest embed, extract, diff, and the --update-manifest mode","feature_path":"/Users/gabadi/workspace/addi/mutate4py/features/manifest.feature","background_hash":"74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b","implementation_hash":"unknown","scenarios":[{"index":1,"name":"the embedded manifest records the required fields","scenario_hash":"762143347a153841cd6aaa6a368a17acf2d93ac3202016cf503f916e409e3dd7","mutation_count":4,"result":{"Total":4,"Killed":4,"Survived":0,"Errors":0},"tested_at":"2026-07-02T03:16:09.701519Z"},{"index":2,"name":"a function unit is recorded with its id, name, range, and hash","scenario_hash":"f1b67b87d293436a66ba3bbfa024a9e52742419da99aeb8812fcaf856402756c","mutation_count":9,"result":{"Total":9,"Killed":9,"Survived":0,"Errors":0},"tested_at":"2026-07-02T03:16:09.701519Z"},{"index":3,"name":"a decorated function records the def line, not the decorator line","scenario_hash":"4eac71c06811061134588d22b5827cec4c37a299f895b1ef3fdc9b8686ce7aa4","mutation_count":1,"result":{"Total":1,"Killed":1,"Survived":0,"Errors":0},"tested_at":"2026-07-02T03:16:09.701519Z"},{"index":6,"name":"extracting a file without a valid manifest yields none","scenario_hash":"0b169723922d2ed700e5740684fde4c34ef67726c9c9d5bef04f8f11403eb7e8","mutation_count":3,"result":{"Total":3,"Killed":3,"Survived":0,"Errors":0},"tested_at":"2026-07-02T03:16:09.701519Z"},{"index":8,"name":"a \"<edit>\" edit leaves the function unchanged in the diff","scenario_hash":"86eb4f8c773a445799ba813c67bea84a62e36fade38280e83e69f16ca96ea12b","mutation_count":10,"result":{"Total":10,"Killed":10,"Survived":0,"Errors":0},"tested_at":"2026-07-02T03:16:09.701519Z"},{"index":9,"name":"diffing previous against current reports the changed id set","scenario_hash":"4fe7165c532385cfb5f5e12d96cbd8466f6b251e9b06210075e56ae6422f2e22","mutation_count":15,"result":{"Total":15,"Killed":15,"Survived":0,"Errors":0},"tested_at":"2026-07-02T03:16:09.701519Z"},{"index":11,"name":"re-running --update-manifest reflects whether anything changed","scenario_hash":"bc90c8304c7e2ed75c747fa17facd4ad5070d5097296ffe52ffd04170abfbe06","mutation_count":9,"result":{"Total":9,"Killed":9,"Survived":0,"Errors":0},"tested_at":"2026-07-02T03:16:09.701519Z"}]}
# acceptance-mutation-manifest-end

Feature: Manifest embed, extract, diff, and the --update-manifest mode

  # TRACKING: F2 (manifest) — docs/adr/0005-manifest-hash-is-ast-unparse.md;
  #           docs/adr/0006-update-manifest-idempotent.md
  #
  # CONTRACT:
  #   Manifest core (embed / extract / diff):
  #     embed(source, manifest) -> source with footer:
  #       <body, trailing newlines trimmed> + "\n\n"
  #       + "# mutate4py-manifest-begin\n# " + <single-line JSON> + "\n"
  #       + "# mutate4py-manifest-end\n"
  #     JSON: { version: 1, tested_at: <RFC3339>, module_hash: <sha256>,
  #             functions: [ { id, name, line, end_line, hash } ] }
  #     extract(source) -> (manifest, true) | (none, false)
  #       finds both markers, strips leading "# " per line, JSON-parses;
  #       missing markers OR parse failure => (none, false), never an error.
  #     diff(previous, current) -> set of changed function ids.
  #   CLI mode:
  #     command: mutate4py <file> --update-manifest
  #     stdout (exit 0): "Updated manifest: <file>"   when it writes
  #                      "Manifest unchanged: <file>" when already current
  #     response (usage error, non-zero exit): <file> missing/unreadable.
  #   NOT in the response: --update-manifest runs no tests, acquires no coverage,
  #     classifies no mutants, and prints no run report (that is F4).
  #
  # CONSTRAINTS:
  #   - Hash = sha256(ast.unparse(subtree)); module_hash = sha256(ast.unparse(stripped module)).
  #     ast.unparse emits canonical source (no positions, no comments) => position-independent;
  #     reformat-only and comment-only edits do NOT change a hash (ADR 0005).
  #   - Function unit range: line = the def/async-def line (node.lineno),
  #     end_line = node.end_lineno; decorators are ABOVE the range.
  #   - Unit ids: func/foo, func/Class.m; nested def/lambda fold in.
  #   - Embed strips any existing manifest first: re-embedding never accretes markers
  #     and the body above the footer is byte-identical to the stripped original.
  #   - diff: previous is none => every current id is changed; else a current id is
  #     changed iff its hash differs from previous; a new id (absent from previous)
  #     is changed; a removed id (in previous, not current) is dropped.
  #   - module_hash is a top-level field; it is NOT part of the per-function diff set.
  #   - --update-manifest is idempotent: it writes (and bumps tested_at) only when the
  #     freshly-built functions/module_hash differ from the embedded manifest (ADR 0006).
  #
  # SEQUENCING: none
  #
  # NFR:
  #   - Extract is the inverse of embed: extract(embed(s, m)) yields m.
  #   - --update-manifest is idempotent: running it twice in a row leaves the file
  #     byte-identical after the first run and prints "Manifest unchanged:" the second.
  #   - tested_at is a well-formed RFC3339 string.
  #
  # SIDE EFFECTS:
  #   - --update-manifest rewrites the source file's manifest footer in place
  #     (only when the manifest changed). No other file is touched.
  #
  # SCOPE:
  #   - Does NOT: decide which sites to mutate from the diff (F4 selection).
  #   - Does NOT: acquire or read coverage (F3).
  #   - Does NOT: own the full flag matrix or mutual-exclusion validation (F5);
  #     F2 ships only --update-manifest's existence, idempotency, and output strings.
  #   - Does NOT: touch --scan's manifest interaction (Changed / Manifest exists) — F5.
  #   - Does NOT: write or restore the .mutate4py.bak crash-safety backup (F4).
  #   - ASSUMED: per-field record correctness (ids, line ranges, hash stability) is
  #     also covered by the manifest module's unit tests; the Gherkin asserts the
  #     observable embed/extract/diff and CLI contract.
  #
  # UX INTENT: none
  # Design artifacts: none

  # manifest-1: embedding writes the marked footer onto a clean file
  Scenario: embedding a manifest appends the marked footer
    Given a Python source file with no embedded manifest
    When a manifest is embedded into the file
    Then the file contains the line "# mutate4py-manifest-begin"
    And the file contains the line "# mutate4py-manifest-end"
    And the manifest JSON line begins with "# "
    And the manifest body above the footer is the original source with trailing newlines trimmed

  # manifest-2: the embedded JSON carries the full record shape
  Scenario Outline: the embedded manifest records the required fields
    Given a Python source file defining "def foo"
    When a manifest is embedded into the file
    And the embedded manifest is extracted
    Then the manifest field "<field>" is present

    Examples:
      | field       |
      | version     |
      | tested_at   |
      | module_hash |
      | functions   |

  # manifest-3: each function record carries its id, name, line range, and hash
  Scenario Outline: a function unit is recorded with its id, name, range, and hash
    Given a Python source file defining "<definition>"
    When a manifest is embedded into the file
    And the embedded manifest is extracted
    Then the first function record has id "<id>" and name "<name>"
    And the first function record has a "line", an "end_line", and a "hash"

    Examples:
      | definition            | id       | name |
      | def foo               | func/foo | foo  |
      | async def foo         | func/foo | foo  |
      | class C with method m | func/C.m | m    |

  # manifest-4: a decorated def excludes the decorator line from its range
  Scenario: a decorated function records the def line, not the decorator line
    Given a Python source file with a decorator above "def foo" on line <def_line>
    When a manifest is embedded into the file
    And the embedded manifest is extracted
    Then the first function record "line" is <def_line>

    Examples:
      | def_line |
      | 2        |

  # manifest-5: a module with no functions records an empty list but a real module_hash
  Scenario: a module with only module-level code records no functions
    Given a Python source file with module-level code and no function definitions
    When a manifest is embedded into the file
    And the embedded manifest is extracted
    Then the manifest "functions" list is empty
    And the manifest "module_hash" is a non-empty hash

  # manifest-6: extract is the inverse of embed
  Scenario: extracting a manifest returns the object that was embedded
    Given a Python source file with no embedded manifest
    When a manifest is embedded into the file
    And the embedded manifest is extracted
    Then the extracted manifest equals the embedded manifest

  # manifest-7: a file with no markers extracts to no manifest
  Scenario Outline: extracting a file without a valid manifest yields none
    Given a Python source file whose footer is "<footer>"
    When the file is extracted
    Then the extract result is "no manifest"

    Examples:
      | footer                                                    |
      | (no markers at all)                                       |
      | # mutate4py-manifest-begin only, no end marker            |
      | both markers around text that is not valid JSON           |

  # manifest-8: re-embedding strips the old footer instead of accreting markers
  Scenario: re-embedding replaces the existing footer
    Given a Python source file with an embedded manifest
    When a manifest is embedded into the file
    Then the file contains exactly one "# mutate4py-manifest-begin" line
    And the manifest body above the footer is byte-identical to the once-embedded body

  # manifest-9: the hash is stable across edits that do not change ast.unparse()
  Scenario Outline: a "<edit>" edit leaves the function unchanged in the diff
    Given a previous manifest built from a function
    And the function is changed by "<edit>"
    When the previous manifest is diffed against the current manifest
    Then the changed function ids are "<changed>"

    Examples:
      | edit                       | changed  |
      | reformatting whitespace    |          |
      | editing a comment          |          |
      | renaming the function      | func/foo |
      | changing a numeric literal | func/foo |
      | changing an operator       | func/foo |

  # manifest-10: diff reports new, changed, and dropped-removed ids per the port
  Scenario Outline: diffing previous against current reports the changed id set
    Given a previous manifest with functions "<previous>"
    And a current manifest with functions "<current>"
    When the previous manifest is diffed against the current manifest
    Then the changed function ids are "<changed>"

    Examples:
      | previous            | current             | changed           |
      | none                | func/a, func/b      | func/a, func/b    |
      | func/a:h1           | func/a:h1           |                   |
      | func/a:h1           | func/a:h2           | func/a            |
      | func/a:h1           | func/a:h1, func/b:h3| func/b            |
      | func/a:h1, func/b:h2| func/a:h1           |                   |

  # manifest-11: --update-manifest writes the footer and reports it
  Scenario: updating the manifest on a file without one writes and reports it
    Given a Python source file with no embedded manifest
    When the command "mutate4py <file> --update-manifest" is run
    Then the output line "Updated manifest: <file>" is printed
    And the file then contains an embedded manifest
    And no test command is run

  # manifest-12: --update-manifest is idempotent under ast.unparse() hashing
  Scenario Outline: re-running --update-manifest reflects whether anything changed
    Given a Python source file with an embedded manifest current as of its content
    And the file is then changed by "<edit>"
    When the command "mutate4py <file> --update-manifest" is run
    Then the output line "<output>" is printed
    And the file footer is "<footer_state>"

    Examples:
      | edit                    | output                       | footer_state           |
      | nothing                 | Manifest unchanged: <file>   | byte-identical         |
      | reformatting whitespace | Manifest unchanged: <file>   | byte-identical         |
      | changing an operator    | Updated manifest: <file>     | rewritten              |

  # manifest-13: --update-manifest on a missing file is a usage error
  Scenario: updating the manifest of a missing file is a usage error
    Given the path "<missing>" does not exist
    When the command "mutate4py <missing> --update-manifest" is run
    Then the command exits with a usage error
    And no manifest is written
