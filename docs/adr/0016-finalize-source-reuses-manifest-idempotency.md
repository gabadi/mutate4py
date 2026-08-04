# ADR 0016 — `_finalize_source` reuses ADR 0006's manifest idempotency in the F4 run loop

- Status: accepted
- Date: 2026-08-04
- Feature: F4 (run loop)
- Spec: docs/spec.md §7 (re-embed manifest)
- Issue: #18

## Context

ADR 0006 made `--update-manifest` idempotent under `ast.dump()` hashing: if the
candidate manifest built from the current source is structurally equal (same
`module_hash`, same per-function hashes; `tested_at` ignored) to the manifest
already embedded, the write is skipped and `tested_at` is not bumped. ADR 0006
explicitly scoped this to F2 only: "does NOT pull in F4's run-loop selection
logic."

`_finalize_source`, the step every scored run (F4) ends in, was left with the
unconditional behavior ADR 0006 replaced elsewhere: it always built a fresh
manifest with the run's `tested_at` and always wrote it, even when every
function/module hash was identical to what was already embedded. A scored run
repeated on unchanged source therefore always produced a diff — pure
`tested_at` churn — that a reviewer had to manually distinguish from a real
change.

Unlike `update_manifest`, `_finalize_source` cannot skip the file write
outright. When `--mutate-all` (or any run with selected sites) executes, the
per-site loop (`_run_mutation_loop` / the parallel workers) repeatedly
overwrites the source file on disk with mutant variants and never reverts —
`_finalize_source`'s write of `clean_source` back to `path` is what restores
correct source after the loop, and that write must keep happening
unconditionally regardless of manifest equality.

## Decision

`_finalize_source` now decides **which manifest dict to embed**, not whether
to write:

1. Build the candidate manifest from `clean_source` with the run's `tested_at`
   (unchanged from before).
2. If the run's pre-existing manifest (extracted from source before the run,
   now threaded through as `existing_manifest`) is structurally equal to the
   candidate (via the same `manifests_structurally_equal` ADR 0006 uses), embed
   the **existing** manifest — preserving its original `tested_at`.
3. Otherwise embed the fresh candidate, exactly as before.

The file write and `.mutate4py.bak` cleanup remain unconditional. Because
`clean_source` is unchanged in the equal case, embedding the same manifest
dict produces bytes identical to what was already on disk/tracked in git —
satisfying "no diff on an unchanged rerun" without needing to skip the write
itself.

The structural-equality choice is factored into a shared `reconcile_manifest`
helper (`_manifest.py`), used by both `update_manifest` (F2) and
`_finalize_source` (F4), so the two call sites share one implementation of
"has anything structural changed" rather than each re-deriving the same
branch.

## Consequences

- `tested_at` in a scored run's embedded manifest now only advances when a
  function or module hash actually changed, matching `--update-manifest`'s
  contract (CONTEXT.md's `tested_at` entry, ADR 0006) — that contract now holds
  for F4 as well as F2.
- `_finalize_source` gained an `existing_manifest: dict | None = None` keyword
  parameter; `_compute_manifest_diff` and `_load_clean_source` now also return
  the extracted pre-run manifest so it can reach `_finalize_source`.
- Recovery/backup behavior (`.mutate4py.bak` removal) is untouched — it stays
  unconditional, independent of the manifest-reuse decision.
