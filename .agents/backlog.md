# Enforcement Gate Backlog

Dated proposals for mechanical enforcement gates, config changes, or CI guardrails.
Format: `<date> | <category> | <failure-class> | <affected> | <status> | <description>`

---
2026-06-25 | project-config | tool-error | all-roles | pending | Disable GPG commit signing in all worktrees' .git/config to eliminate 1Password SSH agent failures (git config --local commit.gpgsign false per worktree, or a global swarm setup step)
2026-06-25 | swarmforge-pattern | tool-error | architect,cleaner | pending | 1Password SSH agent unavailable in swarm sessions causes git fetch and commit signing failures; two roles required manual workaround (-c commit.gpgsign=false); setup-swarm should disable signing in each worktree
2026-06-25 | swarmforge-pattern | tool-error | cleaner,QA,hardender | pending | External GitHub tool installs blocked by auto-mode classifier across 3 roles; engineering.prompt needs explicit fallback rule: "if external install is blocked, use locally installed binary and continue"
2026-06-25 | swarmforge-pattern | tool-error | cleaner,QA,hardender | pending | extract.py returns zero non-null arc content on Claude Code 2.1.191+ across all roles (5 sessions: architect, cleaner, integrator, hardender, QA); investigate JSONL format change and update extract.py
