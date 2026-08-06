# AGENTS.md

Navigation and universal invariants for all agents in this project.

## Roles and Worktrees
- Valid recipient roles: `specifier`, `coder`, `ux-engineer`, `cleaner`, `architect`, `hardender` (two d's), `QA`, `integrator`, `curator`
- Each role maps to `.worktrees/<role>` — use exact spelling; `swarm_handoff.sh` rejects unknown names.

## Local Gates
- `just check` — all CI gates, same order as `.github/workflows/ci.yml` (log-per-gate in `check.log`, ✓/✗ printed, tail on failure). `just check <gate> [<gate> ...]` runs a subset; `just --list` shows public recipes.
- `just mutate <path> [<args>]` — scored mutation run with per-mutant progress captured to a log; only the `Mutation Report` summary is printed. Use this instead of raw `uv run mutate4py <path> --mutate-all` (see `.agents/roles/hardender.md`).

## Tool Paths (Local Machine)
- `crap4py`: installed from local sibling `~/workspace/addi/crap4py` via `uv tool install ~/workspace/addi/crap4py` (not PyPI, not GitHub URL)
- `drywall`: available at `/Users/gabadi/.local/bin/drywall` (not in PyPI under that name)
- `uv run mutate4py` is the correct invocation for mutation scan and manifest checks (not `uvx mutate4py`); uvx isolates the env and breaks self-referential scanning
- `uv run mutate4py src/ --check-manifest` — CI gate; exits 0 if all manifests current, 1 if any are missing/stale

## Tool CLI Signatures
- `gherkin-parser`: requires two args: `gherkin-parser <feature-file> <json-output>`; bare `gherkin-parser <file>` fails with usage error; call WITHOUT `rtk` prefix — rtk breaks it
- `gherkin-mutator`: requires `--feature <feature-file>`, `--generated-dir <dir>`, and `--runner-worker <path>`; no `--help` flag; use `--workers 4` (runner_adapter.py is now concurrent)
- `generate_acceptance.py`: pass just `module_name` (e.g. `run_loop_steps`), NOT `acceptance.steps.module_name` — the generator adds the prefix automatically
- `mutate4py --scan`: accepts exactly ONE file argument; loop over files separately for multi-file scans

## Acceptance Test Safety
- Manifest QA fixtures (`acceptance/fixtures/plain.py`, `acceptance/fixtures/stale.py`) are committed inputs and MUST NOT be overwritten; all manifest QA steps must use a writable-copy pattern (see `acceptance/steps/manifest_qa_steps.py:setup_copy()`)
- `runner_adapter.py` must be executable (`chmod +x`) before gherkin-mutator can use it; tool does not emit a clear permission error; supports `RUNNER_WORKERS` env var (default 4) for concurrent job execution
- When modifying source with an embedded manifest, always strip manifest first, modify body, then re-embed; never append after the manifest footer — `strip_manifest` removes everything from begin-marker to EOF

## Module Dependency Invariants
- `_coverage.py` must not import from `_discovery.py`; if coverage code needs Site objects, move that function to `_discovery.py` (IO-free domain boundary).
- Acceptance step files are boundary files (15-site mutation threshold); extractable pure logic belongs in `*_helpers.py` modules with their own unit tests.
- `coverage_helpers.py` is the testable module for acceptance step helper functions; unit tests live in `tests/test_coverage_helpers.py`.
- `cli_surface_helpers.py` is the testable module for CLI surface acceptance step helpers; unit tests live in `tests/test_cli_surface_helpers.py`.
- `__main__.py` is a pure CLI adapter; `scan_report`, `scan_report_with_coverage`, and `update_manifest` belong in `_runner.py` and are tested directly. Do not move domain functions back to `__main__.py`.

## References
- See `.agents/roles/` for per-role operational rules.
- See `.agents/references/` for deep-dive topics.
- See `.agents/backlog.md` for pending enforcement-gate proposals.
- Role files present: `hardender.md`, `coder.md`, `cleaner.md`, `QA.md`
- `.agents/references/equivalent-mutants.md` — recognized equivalent mutant categories for this project (hardender: no tests needed for these)
