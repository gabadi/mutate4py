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
