---
name: agent-retro
description: Run a conversation retrospective — analyze what happened in this session, what worked, what didn't, and propose concrete improvements. Use when the user says "retro", "retrospective", "what happened in this session", "session review", "what did we do", "analyze this conversation", or when wrapping up a long session. Especially useful after using a skill you're developing. In swarmforge: invoked automatically as the last step before each role goes idle.
compatibility: Primary — requires `entire` CLI (0.6.2+) for transcript extraction. Fallback — Claude Code ~/.claude/projects/ path. Python 3.8+ for the extraction script.
metadata:
  author: gabadi/swarm-forge (fork of giannimassi/agent-retro)
  version: "0.1.0"
---

# agent-retro

## Step 1 — Extract Session Data

**Primary path (entire):**
The extractor script lives next to this SKILL.md at `scripts/extract.py`. Resolve its directory portably (Claude Code sets `$CLAUDE_SKILL_DIR`; pi does not):
```bash
EXTRACT="${CLAUDE_SKILL_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)/..}/scripts/extract.py"; [ -f "$EXTRACT" ] || EXTRACT="scripts/extract.py"
```
If neither resolves, ask the operator for the path to this skill's `scripts/extract.py`.

1. Run `entire session current --json` to get the active session ID and worktree path.
2. Check: does `worktree_path` in the result match `$PWD`?
   - If **NO** (stale result — wrong repo or ended session) → skip `entire session info` entirely; go to **JSONL fallback** below.
   - If **YES** → proceed:
     - Run `entire session info <id> --transcript > /tmp/retro-session.jsonl`
     - Verify: `python3 "$EXTRACT" /tmp/retro-session.jsonl --metadata-only`
     - If verification succeeds, run full extraction: `python3 "$EXTRACT" /tmp/retro-session.jsonl --summary > /tmp/retro-extract.json`
     - Proceed to Step 2 with `/tmp/retro-extract.json`.

**JSONL fallback:**
Use when: `entire` is not installed, `entire session current` returns no session, or `worktree_path` does not match `$PWD`. The fallback depends on the harness — `extract.py` auto-detects the format from the first line (`{"type":"session"` → pi; otherwise Claude Code).

**Claude Code fallback:**
1. Find the Claude Code project dir for this worktree: `ls ~/.claude/projects/ | grep <last-segment-of-PWD>`. Note: dot-prefixed segments encode as double-dash (`.worktrees` → `--worktrees`), so do not use naive `sed` — use `grep` on the last path segment instead.
2. Take the most recently modified `.jsonl` in that dir: `ls -t ~/.claude/projects/<encoded-cwd>/*.jsonl | head -1`.

**pi fallback:**
pi stores sessions under `~/.pi/agent/sessions/<encoded-cwd>/<timestamp>_<uuid>.jsonl`. The encoding wraps the cwd with `--` and replaces every `/`, `\`, and `:` with `-` (so `/Users/gabadi/.agents-skills` → `--Users-gabadi-.agents-skills--`). Dot-prefixed segments are **single**-dashed (`.worktrees/coder` → `-worktrees-coder`), unlike Claude's double-dash — do not reuse the Claude encoding.
1. Encode `$PWD` the same way and locate the dir:
   ```bash
   ENCODED="--$(echo "$PWD" | sed 's|^[/\\]||; s|[/\\:]|-|g')--"
   ls -t ~/.pi/agent/sessions/"$ENCODED"/*.jsonl | head -1
   ```
   If the encoded lookup misses, fall back to `ls ~/.pi/agent/sessions/ | grep "$(basename "$PWD")"` to find the right dir.
2. The most recently modified `.jsonl` in that dir is the current/last session.

**Then (both harnesses):**
3. Verify: `python3 "$EXTRACT" <path> --metadata-only`
4. Run full extraction: `python3 "$EXTRACT" <path> --summary > /tmp/retro-extract.json`

The pi parser produces the same schema as the Claude parser (`conversation_arc`, `tokens.total`, `tokens.estimated_cost_usd`, `tool_result_sizes`, `tools`). `tokens.total` uses the same key names (`input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`) mapped from pi's `usage.{input,output,cacheWrite,cacheRead}`. Cost comes from pi's own `usage.cost.total` when present.

**If no transcript is found:** Report "No session transcript found" and stop. Do not fabricate data.

Raw JSONL is 1MB+ per session — never stream transcript bytes inline into context. Always write to a temp file and pass the path to extract.py.

**Null-arc guard:** Before using the arc, check whether content is populated:
```bash
python3 -c "
import json
d = json.load(open('/tmp/retro-extract.json'))
arc = d.get('conversation_arc', [])
non_null = sum(1 for e in arc if e.get('text') or e.get('content'))
print(f'arc entries: {len(arc)}, non-null content: {non_null}')
"
```
(Both the Claude and pi parsers populate `text`; the guard checks `text` or `content` for compatibility.)
If `non_null == 0` and `len(arc) > 0`, `extract.py` silently failed. Fall back to **in-context reconstruction**: write the retro from live session memory — (1) what tool calls succeeded first try, (2) what failed or needed retries, (3) any user corrections or redirects, (4) token budget marked as `(unavailable — extract.py returned no cost data)`. Do not fabricate metrics.

---

## Step 2 — Read the Conversation Arc

Read `conversation_arc` from `/tmp/retro-extract.json`. This is the full story of the session: every user message and assistant response in order.

Identify:
- User corrections ("no, not that", "stop", "undo", "wrong")
- Redirects (user changing direction mid-task)
- Repeated instructions (same request given more than once)
- Pivots (abandoned approaches)
- Friction moments (back-and-forth on a single point)

---

## Step 3 — Classify Outcomes

Classify what the session produced:
- New code / feature
- Bug fix
- Communication (messages, comments, docs)
- Setup / configuration changes
- Spec or design artifact
- Process improvement
- Review or analysis
- Research
- Skill development

A session may have multiple outcomes.

---

## Step 4 — Analyze What Worked

Identify:
- First-try successes (task completed without corrections)
- Efficient delegation (agents dispatched with clear scope)
- Good skill matches (right skill for the task)
- Clean conversation flow (no redirects)
- Smart tool choice (right tool, right scope)

---

## Step 5 — Analyze What Didn't Work

Identify friction patterns:
- User corrections, redirects, repetitions, stops, frustration signals
- Wasted agent dispatches (dispatched but result unused)
- Oversized tool results (large reads never referenced)
- Tool call retries (same tool called multiple times for the same target)
- Abandoned approaches (started, then discarded)
- Over-engineering (more than the task required)
- Under-specification (task started with insufficient context)

For skill-development retros: read the active SKILL.md (the `${CLAUDE_SKILL_DIR}/SKILL.md` of the skill being developed, or this skill's own `SKILL.md` resolved as above) and identify which instruction caused each friction.

Read `tool_result_sizes` from the extract — flag any tool result over 50KB that was followed by no further reference to that file.

---

## Step 6 — Propose Actions

Lead with the defense-first question: **"What defensive rule did this session's work absorb that future maintainers must keep intact?"** Answer it before cataloging friction — rule-shaped learnings surface before cause-shaped ones.

Capture-first guard: enumerate every candidate learning from Steps 4–5 in full before writing anything to the retro file. Do not filter for "obviousness" or "self-correcting" here — capture everything; the curation stage downstream owns discards.

For each friction pattern, propose one of these action types:
- `skill-update` — change an existing skill. Include before/after text.
- `skill-create` — create a new skill.
- `rule-update` — change a rule or instruction in CLAUDE.md or a role prompt.
- `rule-create` — create a new rule.
- `setup-change` — change a configuration or environment setting.
- `memory-update` — update or create a memory entry.
- `investigate` — flag something for human review (uncertain root cause).
- `acknowledge` — nothing to change; note what worked well.

Be specific. "Improve X" is not a proposal. "Change the wording in Step 3 from Y to Z" is a proposal.

**Scope** — tag every proposed action with exactly one scope value:
- `project` — knowledge about the target project (its code, config, tools, conventions).
- `swarmforge` — knowledge about the harness itself (role prompts, constitution, scripts, pipeline mechanics).
- `skill` — a reusable procedure that should become or amend a skill.
- `ephemeral` — true one-offs; recorded for audit, never promoted.

---

## Step 7 — Write the Retro File

Write to `~/.claude/worklog/retros/YYYY-MM-DD-<slug>.md` where `<slug>` is a 3–5 word kebab-case summary of the session.

Structure:
```markdown
# Session Retro: <slug>
Date: YYYY-MM-DD
Session ID: <id>
Role: <swarmforge role name, or "interactive" outside a swarm>
Branch: <branch>
Duration: <N>m
Cost: $<N>

## Token Budget
| Category | Tokens | Cost |
|---|---|---|
| Input | N | $N |
| Output | N | $N |
| Cache create | N | $N |
| Cache read | N | $N |
| **Total** | **N** | **$N** |

## Tool Result Waste
<table of oversized unused tool results, or "None detected">

## What Worked
<bullet list>

## What Didn't Work
<bullet list with root cause per item>

## Actions
| # | Type | Scope | Description | Target |
|---|------|-------|-------------|--------|
| 1 | skill-update | project | ... | ... |
```

---

## Step 8 — Walk Through Actions

Determine the mode:

**Interactive session (a human is present):**
- Present the retro file path and summary counts (N worked, N didn't work, N actions).
- Walk through each proposed action one by one: show type, scope, description, target. Ask: "Apply? [y/n/defer]". Apply approved actions immediately; mark deferred/skipped in the table.
- After the walkthrough, show the final action table with statuses.

**Autonomous session (swarmforge role, no human in the loop):**
- Do not ask anything. Do not apply any action.
- Mark every action's status as `pending-curation` in the table and finish the retro file.
- The curator role consumes the file downstream; your only job is complete, well-tagged capture.

---

## Step 9 — Preemptive Handoff Recommendation

Check `session` metadata from the extract:
- If `turn_count` > 500, `duration_seconds` > 14400 (4h), or `estimated_cost_usd` > 300:
  - Add a `investigate` action: "Session size threshold reached — consider handoff"
  - Include two ready-to-paste prompts:
    - For `/compact`: "Continue from: <brief state summary>"
    - For `/clear`: "Resume from: <brief state summary> — key context: <3 bullet points>"
