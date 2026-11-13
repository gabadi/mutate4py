# QA Role — Operational Knowledge

## Pre-Handoff Lint and Format Check
Before handing off, MUST run `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`. Fix any failures before handoff. Do not hand off with lint or format violations — integrator absorbs CI fix cycles.

## Shell Counter Files in Acceptance Steps
Shell scripts in acceptance steps must not use `$COUNT` from `ls dir | wc -l` as unique file names with parallel workers — it is not safe under concurrency. Use `$$` (PID) or content-based detection (grep for a token in the worker's source copy) instead.

## Worker Directory Cleanup Assertions
`run_parallel` cleans up `run-PID-NANOS/` (the run-specific subdirectory) but leaves the `workers/` parent directory. Assertions must check for empty run subdirs, not for the absence of `workers/`.
