# Ledger — SwarmForge Items

Work queue for swarmforge-scoped retro actions, prunable.
Format: `<date> | <session-id> | <role> | <failure-class> | <verdict> | <status> | <one-line summary>`

---
2026-06-25 | 9bc9e159 | architect | tool-error | promoted→ledger-swarmforge | pending | SSH/1Password signing failure: determine if swarm sessions should disable GPG signing by default
2026-06-25 | 9bc9e159 | architect | convention-gap | promoted→ledger-swarmforge | pending | Constitution should list canonical role names to eliminate lookup errors
2026-06-25 | 00466112 | cleaner | tool-error | promoted→ledger-swarmforge | pending | crap4py external install blocked by auto-mode; needs permission pre-approval or fallback rule
2026-06-25 | 00466112 | cleaner | tool-error | promoted→ledger-swarmforge | pending | GPG commit fallback: document -c commit.gpgsign=false workaround for 1Password failures
2026-06-25 | 58d11592 | integrator | missing-artifact | promoted→ledger-swarmforge | pending | gtimeout not on macOS; use gh pr checks --watch bare or install coreutils
2026-06-25 | e4b18370 | curator | tool-error | promoted→ledger-swarmforge | pending | gh pr create blocked by auto-mode classifier; consider adding to curator allowed commands
2026-06-25 | a9efd9cb | coder | convention-gap | promoted→ledger-swarmforge | pending | CLI flag names must be cross-checked against feature files before writing step handlers
2026-06-25 | a9efd9cb | coder | convention-gap | promoted→ledger-swarmforge | pending | Write CLI step handlers when feature mixes API+CLI scenarios
2026-06-25 | a9efd9cb | coder | convention-gap | promoted→ledger-swarmforge | pending | Regex step patterns capture concrete values not Gherkin placeholder names
2026-06-25 | ba459785 | hardender | convention-gap | promoted→ledger-swarmforge | pending | Engineering rules mutation table: exception when project IS the mutation tool
2026-06-25 | 4c684992 | QA | tool-error | promoted→ledger-swarmforge | pending | External tool install blocked by sandbox; add fallback-to-local-binary rule to engineering.prompt
2026-06-26 | 34b59cea | specifier | convention-gap | promoted→ledger-swarmforge | pending | Specifier phase 3: for faithful-port features, exhaust upstream source before grilling the user
2026-06-26 | 34b59cea | specifier | convention-gap | promoted→ledger-swarmforge | pending | Contradiction: grill-with-docs skill is disable-model-invocation:true but role says run it autonomously
2026-06-26 | 34b59cea | specifier | missing-artifact | promoted→ledger-swarmforge | pending | ir-dry-checker (specifier phase 6) not installed; reword phase or provide the tool
2026-06-26 | 34b59cea | specifier | tool-error | promoted→ledger-swarmforge | pending | git reset --hard blocked by auto-mode classifier in specifier startup; ready_for_next.sh should own sync
2026-06-26 | ae4e1d02 | cleaner | convention-gap | promoted→ledger-swarmforge | pending | uv run mutate4py is correct (not uvx); uvx isolates env and breaks self-referential scanning
2026-06-26 | 86d7f06f | hardender | convention-gap | promoted→ledger-swarmforge | pending | merge_and_process directive meaning not documented in hardender role; caused 2 extra tool calls
2026-06-26 | 86d7f06f | hardender | convention-gap | promoted→ledger-swarmforge | pending | mutmut 3.x uses --max-children, not --max-workers; role prompt used wrong flag name
2026-06-26 | 48c13d25 | QA | convention-gap | promoted→ledger-swarmforge | pending | git merge origin/<branch> fails for fetched branches; always use local branch name in merge commands
2026-06-26 | f5e87210 | architect | convention-gap | promoted→ledger-swarmforge | pending | Handoff recipient typed from memory instead of conf lookup; already in AGENTS.md but not in architect role checklist
2026-06-26 | f5e87210 | architect | convention-gap | promoted→ledger-swarmforge | pending | Before writing fast-check property tests, grep Object.keys(fc) to avoid unknown-arbitrary failures (fc.hexaString, fc.float 32-bit)
2026-06-26 | 14e97446 | specifier | missing-artifact | promoted→ledger-swarmforge | pending | ir-dry-checker (phase 6) not installed; manual prune required; not recorded so future specifiers hunt for it again
