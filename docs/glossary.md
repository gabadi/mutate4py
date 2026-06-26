# mutate4py — Domain Glossary

Ubiquitous language for the port. Terms are introduced as features need them.

## Manifest (F2)

- **Manifest** — a single JSON object embedded in a source file's footer recording,
  per function unit, the structural hash at the time it was last mutation-tested.
  Lets a later run tell which units changed. Fields: `version`, `tested_at`,
  `module_hash`, `functions[]`.
- **Function unit** — the granularity a manifest tracks and a hash covers. Id forms:
  `func/foo` (top-level `def`/`async def`), `func/Class.m` (method). Nested
  `def`/`lambda` and decorators do **not** create units; their sites fold into the
  enclosing named unit. (Defined in F1 §4; F2 adds line/hash records for it.)
- **Unit hash** — `sha256(ast.dump(subtree))` of the unit's AST node. Position- and
  reformat-independent; changes on rename/literal/operator/re-block edits. See
  ADR 0005.
- **`module_hash`** — `sha256(ast.dump(module))` over the manifest-stripped source.
  A top-level manifest field, separate from per-unit hashes.
- **Embed** — write the manifest into the footer: strip any existing manifest, trim
  trailing newlines, append `\n\n` + begin marker + `\n# ` + JSON + `\n` + end
  marker + `\n`.
- **Extract** — read a manifest back: locate the markers, strip `# ` prefixes,
  JSON-parse. Missing markers or a parse failure ⇒ "no manifest" (not an error).
- **Strip** — remove a manifest footer, returning the source body up to (and one
  trailing newline after) the begin marker. No marker ⇒ source unchanged.
- **Manifest markers** — `# mutate4py-manifest-begin` / `# mutate4py-manifest-end`,
  the comment lines bounding the embedded footer.
- **Changed function IDs** — the diff output: ids whose hash differs from the
  previous manifest, plus **new** ids (no previous entry). **Removed** ids (in
  previous, absent now) are dropped. No previous manifest ⇒ all current ids changed.
- **`tested_at`** — RFC3339 timestamp stamped into the manifest when it is (re)embedded.
  Bumped only when the manifest actually changes (ADR 0006).
- **`--update-manifest`** — the thin CLI mode that rewrites the footer without
  running mutations. Idempotent: prints `Updated manifest: <file>` when it writes,
  `Manifest unchanged: <file>` when the file already matches (ADR 0006).
