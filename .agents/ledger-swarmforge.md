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
2026-06-26 | c53799e5 | architect | tool-error | promoted→ledger-swarmforge | pending | Fork agent stalled (600s watchdog) for architectural review; large swarm-persona context may cause fork hang on open-ended tasks
2026-06-26 | 416dbe9a | cleaner | convention-gap | promoted→ledger-swarmforge | pending | When CRAP/DRY tools recorded as unavailable in memory/AGENTS.md, engineering startup should allow skipping with one-line note
2026-06-26 | 416dbe9a | cleaner | convention-gap | promoted→ledger-swarmforge | pending | --update-manifest not yet implemented; cleaner should note manifest will be stale after src edits until a full run
2026-06-26 | 9fd9fe97 | integrator | convention-gap | promoted→ledger-swarmforge | pending | QA role: before handing off, run ruff check --fix && ruff format and commit if any changes; prevents integrator fix cycles
2026-06-26 | 9fd9fe97 | integrator | convention-gap | promoted→ledger-swarmforge | pending | Integrator: after gh pr merge, if error contains "cannot delete branch" (worktree conflict), treat as success and continue
2026-06-26 | 9fd9fe97 | integrator | convention-gap | promoted→ledger-swarmforge | pending | Verify both ruff check and ruff format in local verification; both are separate CI steps
2026-06-26 | eeab6b91 | QA | convention-gap | promoted→ledger-swarmforge | pending | QA verification: generate coverage LCOV before running crap4py (two-step: uv run coverage run then uv run coverage lcov)
2026-06-26 | a6cab6bf | coder | convention-gap | promoted→ledger-swarmforge | pending | Scope find to src/ or specific subtree, never project root; venv noise bloats results by 50-100x
2026-06-26 | 38ff0a59 | hardender | convention-gap | promoted→ledger-swarmforge | pending | After commit exit-code 128 with signing error, run git log to check if commit succeeded before retrying
2026-06-26 | 4d4d0ea3 | integrator | convention-gap | promoted→ledger-swarmforge | pending | gh pr view without PR number resolves to current branch (swarmforge-integrator), not the feature branch; always pass explicit PR number
2026-06-26 | 4d4d0ea3 | integrator | convention-gap | promoted→ledger-swarmforge | pending | gh pr comment may be blocked in auto-mode; include diagnosis inline in PR body/description as first-choice fallback
2026-06-26 | 61ee6b27 | integrator | convention-gap | promoted→ledger-swarmforge | pending | Integrator: run ruff check && ruff format locally before pushing to confirm all issues resolved in single commit
2026-06-26 | b0229ad6 | QA | missing-artifact | promoted→ledger-swarmforge | pending | QA DRY check: drywall binary download blocked by auto-mode; note SKIPPED if blocked and continue (binary may already exist at ~/.local/bin/drywall)
2026-06-26 | d638c7e4 | QA | convention-gap | promoted→ledger-swarmforge | pending | Stale untracked test artifacts from prior QA sessions may exist in worktree root; prefer git stash -u over rm in auto-mode
2026-06-26 | f585b9ac | architect | convention-gap | promoted→ledger-swarmforge | pending | Fork review prompts for src/ architectural review should include test/ property test files to catch type errors in test consumers
2026-06-26 | 4d4d0ea3 | integrator | convention-gap | promoted→ledger-swarmforge | pending | After gh pr create fails with "already exists", capture PR URL from error output and continue with post-create gate
2026-06-26 | 04c94859 | hardender | convention-gap | promoted→ledger-swarmforge | pending | Hardender: before first mutation run on a file, verify embedManifest format produces valid TS (/* */ wrapped JSON, not raw JSON)
2026-06-26 | 04c94859 | hardender | convention-gap | promoted→ledger-swarmforge | pending | For TS/Bun mutation: use scoped test command per file (bun test test/X.test.ts) not full bun test — 6-8x speedup
2026-06-26 | 52201f30 | coder | convention-gap | promoted→ledger-swarmforge | pending | Integrator handoff payload should signal "verify and forward" vs "implement" to disambiguate passthrough sessions
2026-06-26 | fc5d7a74 | cleaner | convention-gap | promoted→ledger-swarmforge | pending | When adding type aliases, place them after all import statements, never between import blocks
2026-06-26 | 0fe93f63 | coder | convention-gap | promoted→ledger-swarmforge | pending | Coder: before delegating implementation to a fork, run existing unit tests to confirm green baseline; prevents misattributing pre-existing failures
2026-06-26 | b79e3962 | coder | convention-gap | promoted→ledger-swarmforge | pending | When spec text and spec examples contradict, trust examples first; validate algorithm against examples before overriding a fork's working implementation
2026-06-26 | fc327d2f | QA | missing-artifact | promoted→ledger-swarmforge | pending | merge_and_process in PAYLOAD is not a script on PATH for non-hardender roles; all roles must infer: fetch+merge the named commit then run role-specific sequence
2026-06-26 | 38acb0d3 | specifier | convention-gap | promoted→ledger-swarmforge | pending | Completion-cycle git_handoffs reuse fresh-spec payload template, giving no explicit "cycle done" signal; consider a distinct completion-notification type in handoff spec
2026-06-28 | 8c38deb4 | architect | convention-gap | promoted→ledger-swarmforge | pending | Before moving domain functions out of a module, grep tests for direct imports of those function names; prevents post-hoc test-contract repair
2026-06-28 | 8c38deb4 | architect | convention-gap | promoted→ledger-swarmforge | pending | Read existing test signatures for the old function before designing new API — don't discover test contract after implementing
2026-06-28 | 8c38deb4 | architect | convention-gap | promoted→ledger-swarmforge | pending | Extend dependency-rule review phase to include test-import check for functions being moved before touching source file
2026-06-28 | c6b84c63 | architect | convention-gap | promoted→ledger-swarmforge | pending | Think before Edit: if unsure whether a change is correct, articulate why before calling Edit — edit→revert pairs waste turns
2026-06-28 | 4f7feec9 | QA | tool-error | promoted→ledger-swarmforge | pending | tool_result_sizes in extract.py output is a dict (keyed by tool name), not a list; retro SKILL.md Step 5 uses sizes[:5] list slice syntax — schema mismatch causes KeyError
2026-06-28 | 5c32a862 | specifier | convention-gap | promoted→ledger-swarmforge | pending | When request names a flag/behavior the spec marks removed/locked, frontier brief must flag it as a reopenable assumption and ask; do not plan around spec stance as settled
2026-06-28 | 5c32a862 | specifier | convention-gap | promoted→ledger-swarmforge | pending | When a decision reverses, grep for every assertion of the reversed fact across the whole contract (not just the named section) before claiming done
2026-06-28 | b52f13f5 | specifier | convention-gap | promoted→ledger-swarmforge | pending | Default to terse Q→one-line-A when user signals non-expertise or confusion; offer depth on demand; lead dense explanations only when expertise is established
2026-06-28 | b52f13f5 | specifier | convention-gap | promoted→ledger-swarmforge | pending | AskUserQuestion should follow shared mental model; if user answers options with new prerequisite questions, drop to prose and re-ask once rather than re-prompting same decision
2026-06-28 | 3814e69e | cleaner | missing-artifact | promoted→ledger-swarmforge | pending | drywall binary download blocked in auto-mode again (cleaner); pre-install drywall in worktree setup or grant permission in settings.json (duplicate pattern, escalate)
