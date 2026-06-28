# Coder Role — Operational Knowledge

## Dead-Code Guard After Refactor
After extracting a helper function from a function body, immediately delete all stale local variables, intermediate loops, and partial implementations before running tests. Do not rely on test failures (NameError, etc.) to surface dead code — it should be removed proactively as part of the refactor step.

## Acceptance Convenience Wrapper
Before invoking acceptance generation steps manually (`generate_acceptance.py`, `runner_adapter.py`), check for `acceptance/run_acceptance.sh` first — it is the correct entry point and handles sequencing. Calling generation scripts directly without required args fails silently or with cryptic errors.
