# QA Role — Operational Knowledge

## Pre-Handoff Lint and Format Check
Before handing off, MUST run `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`. Fix any failures before handoff. Do not hand off with lint or format violations — integrator absorbs CI fix cycles.

## QA Feature Step Wiring
Before marking QA done, grep `acceptance/run_acceptance.sh` for every `*_qa.feature` file present in `features/`. Confirm each has a `QA_STEPS_MAP` entry. A missing `QA_STEPS_MAP` entry causes silent `SKIP QA: no steps module for X` output — the feature is silently skipped and failures are masked.
