Feature: Manifest embed, extract, diff, and the --update-manifest mode

  # TRACKING: F2 (manifest) — docs/plan.md; docs/spec.md §5 (manifest), §4 (units),
  #           §8 (--update-manifest output);
  #           docs/adr/0004-manifest-faithful-port-of-mutate4go.md;
  #           docs/adr/0005-manifest-hash-is-ast-dump.md;
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
  #   - Hash = sha256(ast.dump(subtree)); module_hash = sha256(ast.dump(stripped module)).
  #     ast.dump default args (no include_attributes) => position-independent;
  #     reformat-only and comment-only edits do NOT change a hash (ADR 0005).
  #   - Function unit range: line = the def/async-def line (node.lineno),
  #     end_line = node.end_lineno; decorators are ABOVE the range (ADR 0004).
  #   - Unit ids follow F1 §4: func/foo, func/Class.m; nested def/lambda fold in.
  #   - Embed strips any existing manifest first: re-embedding never accretes markers
  #     and the body above the footer is byte-identical to the stripped original.
  #   - diff: previous is none => every current id is changed; else a current id is
  #     changed iff its hash differs from previous; a new id (absent from previous)
  #     is changed; a removed id (in previous, not current) is dropped (ADR 0004).
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
    Given a Python source file with a decorator on line <decorator_line> and "def foo" on line <def_line>
    When a manifest is embedded into the file
    And the embedded manifest is extracted
    Then the first function record "line" is <def_line>

    Examples:
      | decorator_line | def_line |
      | 1              | 2        |

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

  # manifest-9: the hash is stable across edits that do not change ast.dump()
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

  # manifest-12: --update-manifest is idempotent under ast.dump() hashing
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
