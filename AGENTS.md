# AGENTS.md

Navigation and universal invariants for all agents in this project.

## Roles and Worktrees
- Valid recipient roles: `specifier`, `coder`, `ux-engineer`, `cleaner`, `architect`, `hardender` (two d's), `QA`, `integrator`, `curator`
- Each role maps to `.worktrees/<role>` — use exact spelling; `swarm_handoff.sh` rejects unknown names.

## Tool Paths (Local Machine)
- `crap4py`: installed from local sibling `~/workspace/addi/crap4py` via `uv tool install ~/workspace/addi/crap4py` (not PyPI, not GitHub URL)
- `drywall`: available at `/Users/gabadi/.local/bin/drywall` (not in PyPI under that name)
- `mutmut`: standard Python mutation tool; use on this project's own test suite

## References
- See `.agents/roles/` for per-role operational rules.
- See `.agents/references/` for deep-dive topics.
- See `.agents/backlog.md` for pending enforcement-gate proposals.
- Role files present: `hardender.md`
