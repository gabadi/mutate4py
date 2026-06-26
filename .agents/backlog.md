# Enforcement Gate Backlog

Dated proposals for mechanical enforcement gates, config changes, or CI guardrails.
Format: `<date> | <category> | <failure-class> | <affected> | <status> | <description>`

---
2026-06-25 | project-config | tool-error | all-roles | pending | Disable GPG commit signing in all worktrees' .git/config to eliminate 1Password SSH agent failures (git config --local commit.gpgsign false per worktree, or a global swarm setup step)
2026-06-25 | swarmforge-pattern | tool-error | architect,cleaner | pending | 1Password SSH agent unavailable in swarm sessions causes git fetch and commit signing failures; two roles required manual workaround (-c commit.gpgsign=false); setup-swarm should disable signing in each worktree
2026-06-25 | swarmforge-pattern | tool-error | cleaner,QA,hardender | pending | External GitHub tool installs blocked by auto-mode classifier across 3 roles; engineering.prompt needs explicit fallback rule: "if external install is blocked, use locally installed binary and continue"
2026-06-25 | swarmforge-pattern | tool-error | cleaner,QA,hardender | pending | extract.py returns zero non-null arc content on Claude Code 2.1.191+ across all roles (5 sessions: architect, cleaner, integrator, hardender, QA); investigate JSONL format change and update extract.py
2026-06-26 | swarmforge-pattern | tool-error | specifier,coder,cleaner,architect,hardender,QA | pending | extract.py arc null-content now confirmed across 9+ sessions and 6 roles in CC 2.1.193; this is now critical-path for all agent-retro data analysis — ESCALATE
2026-06-26 | swarmforge-pattern | convention-gap | specifier,specifier | pending | ir-dry-checker (specifier phase 6) is not installed; two specifier sessions in this pipeline hit it; either ship the tool or reword phase 6 to manual-prune
2026-06-26 | swarmforge-pattern | convention-gap | specifier,architect | pending | role-level tool API discovery gap: both specifier (grill-with-docs invocation failure) and architect (fc.hexaString/fc.float missing) were blocked by undocumented API surfaces; add "run --help or grep available API before using any unfamiliar tool/library function" to constitution
2026-06-26 | swarmforge-pattern | convention-gap | cleaner,QA,integrator | pending | pre-handoff lint+format verification gap: cleaner and QA do not run ruff check+format before handing off; integrator absorbs 2+ fix-push-watch cycles per pipeline run; add mandatory pre-handoff lint+format step to engineering verification
2026-06-26 | swarmforge-pattern | missing-artifact | coder,QA | pending | drywall DRY check blocked by auto-mode sandbox across 2 roles attempting binary download; pre-install drywall in worktree setup or grant explicit permission in project settings.json
2026-06-26 | swarmforge-pattern | missing-artifact | QA,cleaner | pending | merge_and_process <role> <commit> appears in handoff PAYLOADs for non-hardender roles but no such script exists; both QA and cleaner had to infer the merge intent manually; either ship the script for all roles or update handoff spec to document the convention
