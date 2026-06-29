# QA Role — Operational Knowledge

## Pre-Handoff Lint and Format Check
Before handing off, MUST run `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`. Fix any failures before handoff. Do not hand off with lint or format violations — integrator absorbs CI fix cycles.

## QA Feature Step Wiring
Before marking QA done, grep `acceptance/run_acceptance.sh` for every `*_qa.feature` file present in `features/`. Confirm each has a `QA_STEPS_MAP` entry. A missing `QA_STEPS_MAP` entry causes silent `SKIP QA: no steps module for X` output — the feature is silently skipped and failures are masked.

## QA Harness: Handling CLI-Rejected Values (e.g. --max-workers 0)
When a QA feature passes a value that the CLI rejects (e.g., `--max-workers 0` to test serial mode), handle it in `_run_qa_cmd` — not by changing the CLI validator. Changing the CLI validator to accept test-only values breaks the cli-surface acceptance test.

## Shell Counter Files in Acceptance Steps
Shell scripts in acceptance steps must not use `$COUNT` from `ls dir | wc -l` as unique file names with parallel workers — it is not safe under concurrency. Use `$$` (PID) or content-based detection (grep for a token in the worker's source copy) instead.

## Worker Directory Cleanup Assertions
`run_parallel` cleans up `run-PID-NANOS/` (the run-specific subdirectory) but leaves the `workers/` parent directory. Assertions must check for empty run subdirs, not for the absence of `workers/`.
