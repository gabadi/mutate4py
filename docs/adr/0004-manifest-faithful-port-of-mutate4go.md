# ADR 0004 — Manifest is a faithful port of mutate4go's `manifest.go`

- Status: accepted
- Date: 2026-06-26
- Feature: F2 (`manifest`)
- Spec: docs/spec.md §5 (manifest), §4 (function units)
- Port source: `github.com/unclebob/mutate4go` `internal/manifest/manifest.go`,
  `internal/mutations/mutations.go`

## Context

F2 embeds, extracts, and diffs a manifest in the source-file footer. The design
question is not "what should it do" but "what does mutate4go do" — F2 is a port.
The only sanctioned divergence is the hash function (§5 [PY], see ADR 0005). Every
other behaviour below is read straight from `manifest.go` / `mutations.go` and
mapped to Python's `ast`.

## Decision — direct port mapping

**Markers and footer format** (`Strip`/`Embed`):
- Begin/end markers use `#` comments (Go uses `//`): `# mutate4py-manifest-begin`,
  `# mutate4py-manifest-end`.
- `Strip`: find begin marker; `TrimRight(content[:start], "\n") + "\n"`. No marker
  ⇒ return content unchanged.
- `Embed`: strip first, then `TrimRight(clean,"\n") + "\n\n" + begin + "\n# " +
  json + "\n" + end + "\n"`. JSON is a single line; the `# ` prefix is the only
  thing between the begin marker's newline and the JSON.

**Extract** (`Extract`):
- Require both markers, `end > start`; otherwise "no manifest".
- Take the block between markers, per line `strip → drop leading "#" → strip`,
  drop empties, join, JSON-parse. Parse failure ⇒ "no manifest" (not an error).

**Record shape** (`Manifest` / `Function` structs):
- Top level: `version` (always `1`), `tested_at` (RFC3339), `module_hash`,
  `functions[]`.
- Per function: `id, name, line, end_line, hash` — same field names, same JSON keys.

**Function unit line range** (`extractFunctions`):
- mutate4go: `StartLine = fn.Pos().Line`, `EndLine = fn.End().Line` — the `func`
  keyword line through the closing brace line.
- mutate4py [PY] mapping: `line = node.lineno` (the `def`/`async def` line),
  `end_line = node.end_lineno`. **Decorators are excluded from the range** — they
  are `node.decorator_list`, positioned above `node.lineno`; Go has no decorators,
  and §4 says "decorators do not create units; the decorated def is the unit", so
  the unit's range is the `def` itself. (Decorators still affect the *hash* because
  they are part of the dumped subtree — see ADR 0005.)
- Unit `id`/`name` come from F1's existing `_format_function_id` logic
  (`func/foo`, `func/Class.m`); F2 adds only the `line`/`end_line`/`hash` fields,
  which F1's `Site` did not carry.

**Diff** (`ChangedFunctionIDs`):
- `previous is None` ⇒ every current function `id` is changed.
- Otherwise build `{id: hash}` from previous; a current `id` is changed iff
  `previous_hash_for_id != current_hash`. A **new** id (absent from previous) is
  changed (no prior hash to match). A **removed** id (in previous, not current) is
  **silently dropped** — the diff iterates `current` only.
- `module_hash` is a top-level field; it is NOT part of the per-function changed
  set. (Run-loop F4 decides how to use `module_hash`; F2 only records and diffs.)

**Crash-safety backup** (`SaveBackup`/`RestoreBackup`/`CleanupBackup`):
- Out of F2 scope — exercised by the run loop (F4). F2 ships embed/extract/diff +
  the thin `--update-manifest` mode only. The `.mutate4py.bak` path constant is
  noted for F4.

## Consequences

- The manifest module is a near-mechanical translation; reviewers compare it
  line-for-line against `manifest.go`. The only places allowed to differ are the
  marker string, the comment prefix, and the hash function (ADR 0005).
- "Removed function silently dropped" is faithful and intentional: a deleted
  function has nothing to re-mutation-test.
