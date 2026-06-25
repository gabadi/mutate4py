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
