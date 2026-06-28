# Ledger — Project Knowledge

Permanent, append-only. Contains only `promoted` and `rejected→first-occurrence` items.
Format: `<date> | <session-id> | <role> | <failure-class> | <verdict> | <one-line summary>`

---
2026-06-25 | 9bc9e159 | architect | convention-gap | promoted→AGENTS.md | Correct role name spelling: hardender (two d's); worktree dir names are authoritative
2026-06-25 | 9bc9e159 | architect | tool-error | rejected→first-occurrence | extract.py null-arc: all arc entries return null content on Claude Code 2.1.191
2026-06-25 | 00466112 | cleaner | missing-artifact | promoted→AGENTS.md | drywall at /Users/gabadi/.local/bin/drywall (not in PyPI); crap4py from local sibling
2026-06-25 | 58d11592 | integrator | tool-error | rejected→first-occurrence | extract.py null-arc: integrator session confirms pattern (same failure class)
2026-06-25 | e4b18370 | curator | tool-error | rejected→first-occurrence | agent-retro: use grep -A50 "## Actions" instead of cat to read retros (full dump = 4-6x larger)
2026-06-25 | ba459785 | hardender | convention-gap | promoted→.agents/roles/hardender.md | mutate4py is the mutation tool — use mutmut on this project's own test suite, not itself
2026-06-25 | ba459785 | hardender | missing-artifact | promoted→AGENTS.md | crap4py installed from local sibling ~/workspace/addi/crap4py (not PyPI or GitHub URL)
2026-06-25 | ba459785 | hardender | missing-artifact | rejected→first-occurrence | gherkin-mutator --help not supported; read source to find --feature flag
2026-06-25 | 4c684992 | QA | tool-error | rejected→first-occurrence | extract.py null-arc: QA session confirms pattern (5th role reporting same failure)
2026-06-26 | ae4e1d02 | cleaner | convention-gap | promoted→AGENTS.md | uv run mutate4py is correct invocation; uvx breaks self-referential scanning
2026-06-26 | 93e42778 | coder | convention-gap | promoted→.agents/roles/coder.md | dead-code guard: delete stale partial impl after extracting a helper, before running tests
2026-06-26 | 93e42778 | coder | convention-gap | rejected→first-occurrence | Gherkin label "renaming the function" ambiguous (function vs parameter rename); specifier should clarify
2026-06-26 | 86d7f06f | hardender | convention-gap | promoted→.agents/roles/hardender.md | merge_and_process means git merge + hardening sequence, not a script on PATH
2026-06-26 | 86d7f06f | hardender | convention-gap | promoted→.agents/roles/hardender.md | mutmut 3.x uses --max-children not --max-workers
2026-06-26 | ba459785 | hardender | missing-artifact | promoted→AGENTS.md | gherkin-mutator flags: --feature, --generated-dir required; no --help; defaults to features/a-feature.feature
2026-06-26 | 48c13d25 | QA | convention-gap | promoted→AGENTS.md | manifest QA fixtures are committed inputs; all manifest QA steps must use writable-copy pattern
2026-06-26 | 14e97446 | specifier | convention-gap | promoted→AGENTS.md | gherkin-parser requires two args: gherkin-parser <feature-file> <json-output>
2026-06-26 | d24200ea | architect | convention-gap | promoted→AGENTS.md | _coverage.py must not import _discovery.py; IO-near code must not depend on IO-free domain types
2026-06-26 | b2aa029b | cleaner | convention-gap | promoted→AGENTS.md | acceptance step files are boundary files (15-site threshold); pure logic belongs in *_helpers.py modules
2026-06-26 | b2aa029b | cleaner | convention-gap | promoted→AGENTS.md | coverage_helpers.py is testable module for acceptance step helper functions; tests in tests/test_coverage_helpers.py
2026-06-26 | b2aa029b | cleaner | convention-gap | rejected→first-occurrence | agent-retro step 5: scan site list for per-pattern contributors before starting boundary-file mutation-site reduction
2026-06-26 | c53799e5 | architect | tool-error | rejected→first-occurrence | fork agent stalled (600s) when dispatched for open-ended architectural review with large inherited context
2026-06-26 | 0fe93f63 | coder | convention-gap | promoted→AGENTS.md | gherkin-parser must be called without rtk prefix; rtk breaks it
2026-06-26 | 0fe93f63 | coder | convention-gap | promoted→AGENTS.md | generate_acceptance.py: pass just module_name, not acceptance.steps.module_name
2026-06-26 | 0fe93f63 | coder | convention-gap | promoted→AGENTS.md | strip+modify+re-embed pattern: when modifying source with embedded manifest, strip first then re-embed
2026-06-26 | bb18021c | architect | convention-gap | rejected→first-occurrence | apply_mutant must stay in _discovery.py alongside Site and line-index helpers; do not re-extract
2026-06-26 | f72497fa | cleaner | convention-gap | promoted→AGENTS.md | mutate4py --scan accepts one file at a time; loop over files separately
2026-06-26 | da863ce7 | hardender | convention-gap | promoted→.agents/roles/hardender.md | mutmut run takes mutant-name patterns, not file paths; use bare mutmut run to run all
2026-06-26 | da863ce7 | hardender | convention-gap | promoted→AGENTS.md | runner_adapter.py must be executable (chmod +x) before gherkin-mutator can use it
2026-06-26 | da863ce7 | hardender | convention-gap | promoted→.agents/references/equivalent-mutants.md | five equivalent mutant categories for this project (falsy None, argparse dest, help-text, single-comma DA, single-op compare)
2026-06-28 | 976a22ac | hardender | convention-gap | promoted→.agents/roles/hardender.md | mutmut v3 module-path filtering fails (AssertionError); always run `mutmut run --max-children 8` first to populate stats before filtering
2026-06-28 | 976a22ac | hardender | convention-gap | promoted→.agents/roles/hardender.md | gherkin-mutator uses --feature <path> (named), not positional; check Clojure source at /tmp/aps-build/bb/... if CLI unclear
2026-06-28 | dc019dd9 | cleaner | convention-gap | promoted→.agents/roles/cleaner.md | boundary file 15-site threshold is a trigger not hard gate; document irreducible minimum when all testable logic is extracted
2026-06-28 | dc019dd9 | cleaner | convention-gap | promoted→.agents/roles/cleaner.md | when writing test for refactored function, verify error message strings match new implementation — do not copy from old code
2026-06-28 | a80e933d | integrator | convention-gap | promoted→.agents/roles/QA.md | QA must run ruff check+format before handoff (recurrence of 9fd9fe97); QA.md created with pre-handoff verification rule
2026-06-28 | 4f7feec9 | QA | convention-gap | promoted→.agents/roles/QA.md | before marking QA done, grep run_acceptance.sh for every *_qa.feature and confirm QA_STEPS_MAP entry exists; silent skip masks test failures
2026-06-28 | 3d5cea42 | coder | convention-gap | promoted→.agents/roles/coder.md | check for run_acceptance.sh wrapper before invoking acceptance generation scripts directly; scripts require positional args and fail silently
2026-06-28 | 3814e69e | cleaner | convention-gap | promoted→.agents/roles/cleaner.md | manifest "NEW" hashes after coder handoff are expected; do not hand-edit — mutation tool refreshes them on first scan
2026-06-28 | 8c38deb4 | architect | convention-gap | promoted→AGENTS.md | __main__.py is CLI adapter only; scan_report/scan_report_with_coverage/update_manifest belong in _runner.py and are tested directly
2026-06-28 | dc019dd9 | cleaner | convention-gap | promoted→AGENTS.md | cli_surface_helpers.py is testable module for CLI surface step helpers; tests in tests/test_cli_surface_helpers.py
