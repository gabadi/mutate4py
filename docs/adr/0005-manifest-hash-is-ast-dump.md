# ADR 0005 — Manifest hash is SHA-256 of `ast.dump()`, not whitespace-collapsed text

- Status: accepted
- Date: 2026-06-26
- Feature: F2 (`manifest`)
- Spec: docs/spec.md §5 (the locked [PY] divergence)
- Port source: `mutate4go` `manifest.go` `hash()` / `normalize()`

## Context

mutate4go hashes a function unit as `sha256(normalize(fn.Text))` where
`normalize = strings.Join(strings.Fields(value), " ")` — collapse all runs of
whitespace to single spaces, then SHA-256. Its `module_hash` is the same over the
manifest-stripped file content. Contract: *any textual edit re-tests* (a reformat
changes the text, hence the hash).

This is the one place F2 is **not** a faithful port. Whitespace-collapse is wrong
for Python: indentation is syntactically significant (it defines block structure),
so `strings.Fields` would treat a re-indent that moves a statement in or out of a
block as identical to the original — silently dropping re-tests on a real
behaviour change. Spec §5 locks the divergence.

## Decision

- **Unit hash** = `sha256(ast.dump(subtree))` where `subtree` is the unit's parsed
  AST node (the `FunctionDef`/`AsyncFunctionDef`, decorators included).
- **`module_hash`** = `sha256(ast.dump(module))` where `module` is the parse of the
  **manifest-stripped** source.
- `ast.dump()` is called with its **default** arguments — `include_attributes` is
  left `False`, so line/column positions are NOT in the dump. The hash is therefore
  **position-independent**: moving a function within the file does not change its
  hash (matching mutate4go's `normalize`, which also drops line numbers).
- What changes the hash: rename, literal/number change, operator change,
  re-blocking (re-indent that changes structure), decorator change. What does NOT:
  reformatting within a statement, comment edits, blank-line changes, moving the
  function. This is the deliberate, spec-locked Python contract.

## Consequences

- Re-tests are driven by behaviour-affecting edits, not textual churn — stronger
  than mutate4go for Python, weaker (intentionally) for reformat-only edits.
- The `line`/`end_line` fields in the manifest are recorded for human/diff use but
  are NOT part of the hash, so they can change freely (a function moving down the
  file updates `line` but keeps its `hash`, so it is not re-tested). This is correct.
- Hashing the dumped *subtree* (not re-parsing a text slice) means F2 needs the
  unit's AST node, not just its line range — an input F1's `Site` did not expose
  (see ADR 0004).
