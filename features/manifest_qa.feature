Feature: QA — the manifest is observable end-to-end through the --update-manifest CLI

  # TRACKING: F2 (manifest) — docs/adr/0005-manifest-hash-is-ast-unparse.md;
  #           docs/adr/0006-update-manifest-idempotent.md
  #
  # CONTRACT:
  #   End-to-end QA for F2. Operates ONLY through the user interface: the
  #   `mutate4py <file> --update-manifest` command, its printed line, and the
  #   resulting file on disk. No project API — QA never imports mutate4py or calls
  #   embed/extract/diff directly.
  #   The QA agent runs the command against a writable copy of a committed fixture
  #   and asserts on: the printed line ("Updated manifest: <file>" /
  #   "Manifest unchanged: <file>"), the exit code, and the bytes of the file
  #   (footer present / absent / byte-identical between runs).
  #
  # CONSTRAINTS:
  #   - QA works on a writable COPY of each committed fixture, since
  #     --update-manifest rewrites the file in place.
  #   - The footer is observed by reading the file's text and looking for the
  #     "# mutate4py-manifest-begin" / "# mutate4py-manifest-end" marker lines —
  #     a user could do the same with a text editor. No JSON-field assertions here
  #     (field-level shape is the manifest.feature / unit-test concern).
  #   - Idempotency is observed by byte-comparing the file before and after a second
  #     run, and by the printed line — not by inspecting hashes.
  #   - No coverage file is supplied; --update-manifest must not need one.
  #
  # SEQUENCING: none
  #
  # NFR:
  #   - Idempotent: a second --update-manifest with no edit leaves the file
  #     byte-identical and prints "Manifest unchanged: <file>".
  #
  # SIDE EFFECTS:
  #   - --update-manifest rewrites the fixture copy's footer in place (only when the
  #     manifest changed).
  #
  # SCOPE:
  #   - Does NOT: assert run-report, coverage, or killed/survived output (F4).
  #   - Does NOT: assert --scan's Changed / Manifest exists interaction through
  #     Gherkin — --scan does read the manifest (issue #46; see site-discovery.feature
  #     for its no-manifest scenarios and tests/test_main.py for the manifest-present
  #     case) but no QA scenario here drives --scan against a real manifest.
  #   - Does NOT: assert internal JSON field values (manifest.feature covers shape).
  #   - ASSUMED: `mutate4py <file> --update-manifest` is the user-facing invocation,
  #     prints one status line to stdout, and exits 0 on success.
  #
  # UX INTENT: none
  # Design artifacts: none

  Background:
    Given the mutate4py command-line tool is installed
    And a writable copy of a committed Python fixture

  # qa-manifest-1: updating a manifest-free file writes the footer and reports it
  Scenario: updating a fixture without a manifest writes the footer
    Given a fixture copy "plain.py" with no embedded manifest
    When the command "mutate4py plain.py --update-manifest" is run
    Then the command exits successfully
    And the output line "Updated manifest: plain.py" is printed
    And the file "plain.py" then contains a "# mutate4py-manifest-begin" line
    And the file "plain.py" then contains a "# mutate4py-manifest-end" line

  # qa-manifest-2: a second update with no edit is a no-op and says so
  Scenario: re-running update on an unchanged file reports it unchanged
    Given a fixture copy "plain.py" that already has a current embedded manifest
    And a recorded copy of its bytes
    When the command "mutate4py plain.py --update-manifest" is run
    Then the output line "Manifest unchanged: plain.py" is printed
    And the file "plain.py" on disk matches the recorded bytes exactly

  # qa-manifest-3: a behaviour-affecting edit makes update rewrite the footer
  Scenario: updating after an operator change rewrites the footer
    Given a fixture copy "plain.py" with a current embedded manifest
    And the fixture copy is edited to change an operator
    When the command "mutate4py plain.py --update-manifest" is run
    Then the output line "Updated manifest: plain.py" is printed
    And the file "plain.py" still contains exactly one "# mutate4py-manifest-begin" line

  # qa-manifest-4: a reformat-only edit leaves the manifest unchanged
  Scenario: updating after a whitespace-only edit reports unchanged
    Given a fixture copy "plain.py" with a current embedded manifest
    And the fixture copy is edited by reformatting whitespace only
    When the command "mutate4py plain.py --update-manifest" is run
    Then the output line "Manifest unchanged: plain.py" is printed

  # qa-manifest-5: updating a missing file is a usage error that writes nothing
  Scenario: updating a path that does not exist fails as a usage error
    Given no file exists at "does_not_exist.py"
    When the command "mutate4py does_not_exist.py --update-manifest" is run
    Then the command exits with a non-zero status
    And no "Updated manifest:" line is printed
    And no file is created at "does_not_exist.py"

  # qa-manifest-6: re-embedding never accretes a second footer
  Scenario: updating a file that already has a manifest keeps a single footer
    Given a fixture copy "stale.py" with an embedded manifest that is out of date
    When the command "mutate4py stale.py --update-manifest" is run
    Then the output line "Updated manifest: stale.py" is printed
    And the file "stale.py" contains exactly one "# mutate4py-manifest-begin" line
    And the file "stale.py" contains exactly one "# mutate4py-manifest-end" line
