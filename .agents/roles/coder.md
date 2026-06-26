# Coder Role — Operational Knowledge

## Dead-Code Guard After Refactor
After extracting a helper function from a function body, immediately delete all stale local variables, intermediate loops, and partial implementations before running tests. Do not rely on test failures (NameError, etc.) to surface dead code — it should be removed proactively as part of the refactor step.
