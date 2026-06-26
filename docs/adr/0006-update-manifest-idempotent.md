# ADR 0006 — `--update-manifest` is idempotent; prints `Manifest unchanged: <file>` on a no-op

- Status: accepted
- Date: 2026-06-26
- Feature: F2 (`manifest`)
- Spec: docs/spec.md §5, §8 (`Updated manifest: <file>`); §2 (`--update-manifest`)
- Port source: `mutate4go` `runner.go` `UpdateManifest`

## Context

F2 ships a thin `--update-manifest` CLI mode (pulled forward from F5 per the plan
amendment) so the manifest core is observable end-to-end — mirroring how F1 shipped
`--scan`. mutate4go's `UpdateManifest` (runner.go:151) is unconditional: read,
strip, discover, `Build(..., time.Now())`, `Embed`, `WriteFile`, print
`Updated manifest: <path>` — every run rewrites the footer with a fresh `tested_at`.

Under mutate4go's text-hash this is harmless churn (a re-run with no edit produces
an identical footer except `tested_at`). Under mutate4py's `ast.dump()` hash
(ADR 0005), a reformat-/comment-only edit produces a byte-identical `functions`
array and `module_hash` — so an unconditional rewrite would bump `tested_at` and
re-write the footer on a run where, by the spec's own hashing, nothing testable
changed. That pollutes the file and any PR diff containing it.

## Decision

`--update-manifest` is **idempotent under `ast.dump()` hashing**:

1. Read source; `Extract` any existing manifest.
2. Strip manifest; discover units; `Build` the candidate manifest (new
   `module_hash` + per-unit `hash`).
3. Compare the candidate's `module_hash` and `functions` (`id` + `hash`, ignoring
   `tested_at`) to the extracted manifest.
   - **Equal** ⇒ do NOT write, do NOT bump `tested_at`. Print
     `Manifest unchanged: <file>`.
   - **Different, or no existing manifest** ⇒ `Embed` and write the file with the
     fresh `tested_at`. Print `Updated manifest: <file>`.

`Updated manifest: <file>` is the spec §8 string, unchanged.
`Manifest unchanged: <file>` is a **new** string not in spec §8, introduced by this
ADR; user-confirmed wording.

The comparison reuses F2's own `Extract` + `Build` primitives — it does NOT pull in
F4's run-loop selection logic. "Has anything structural changed since the embedded
manifest" is exactly the F2 diff, applied to the file against itself.

## Consequences

- Divergence from mutate4go's unconditional rewrite — recorded here so the coder
  and QA do not "fix" it back to the port. Justified solely by the ADR 0005 hash
  divergence; without `ast.dump()` this idempotency would not be needed.
- The `_qa.feature` asserts both strings: re-running `--update-manifest` on an
  already-current file prints `Manifest unchanged:` and leaves the file
  byte-identical; running after a structural edit prints `Updated manifest:` and
  changes the footer.
- F5 later wires `--update-manifest` into the mutual-exclusion matrix
  (exclusive with `--scan` and execution options); F2 owns only its existence,
  idempotency, and the two output strings.
