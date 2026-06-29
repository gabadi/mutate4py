# Coder Role — Operational Knowledge

## Dead-Code Guard After Refactor
After extracting a helper function from a function body, immediately delete all stale local variables, intermediate loops, and partial implementations before running tests. Do not rely on test failures (NameError, etc.) to surface dead code — it should be removed proactively as part of the refactor step.

## Acceptance Convenience Wrapper
Before invoking acceptance generation steps manually (`generate_acceptance.py`, `runner_adapter.py`), check for `acceptance/run_acceptance.sh` first — it is the correct entry point and handles sequencing. Calling generation scripts directly without required args fails silently or with cryptic errors.

## Merge Handoff: Verify Public API Signatures
After receiving a merge-result handoff (hardener or cleaner branch merged onto a feature branch), diff the public function signatures of all touched modules against their pre-merge state before running tests. A merge can silently revert API contract changes (e.g., function signature, return type); in a dynamically-typed project this manifests as a runtime TypeError, not a compile error.
