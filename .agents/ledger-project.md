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
