# AGENTS.md

Navigation and universal invariants for all agents in this project.

## Roles and Worktrees
- Valid recipient roles: `specifier`, `coder`, `ux-engineer`, `cleaner`, `architect`, `hardender` (two d's), `QA`, `integrator`, `curator`
- Each role maps to `.worktrees/<role>` — use exact spelling; `swarm_handoff.sh` rejects unknown names.

## Local Gates
- `just check` — all CI gates, same order as `.github/workflows/ci.yml` (log-per-gate in `check.log`, ✓/✗ printed, tail on failure). `just check <gate> [<gate> ...]` runs a subset; `just --list` shows public recipes.
- `just mutate <path> [<args>]` — scored mutation run with per-mutant progress captured to a log; only the `Mutation Report` summary is printed. Use this instead of raw `uv run mutate4py <path>` (see `.agents/roles/hardender.md`).
- While iterating on a change, run `just check test-unit` (make the behaviour work first); the full `just check` runs once before handing off or committing.

## Code Review
- Use `/mattpocock-skills:code-review`, never bare `/code-review` (different, heavier skill).

## Tool Paths (Local Machine)
- `crap4py`: installed from local sibling `~/workspace/addi/crap4py` via `uv tool install ~/workspace/addi/crap4py` (not PyPI, not GitHub URL)
- `drywall` and `gherkin-parser` (not in PyPI): run `just install-tools` once per machine. It installs the versions pinned in the `justfile` (`DRYWALL_TAG`, `GHERKIN_PARSER_COMMIT`) into `~/.local/bin`, the same pins CI installs with, and rerunning it is a no-op. `~/.local/bin` must be on PATH. When either tool is missing, `just check` fails before its first gate and names this recipe.
- `uv run mutate4py` is the correct invocation for mutation scan and manifest checks (not `uvx mutate4py`); uvx isolates the env and breaks self-referential scanning
- `uv run mutate4py src/ --check-manifest --manifest-file` — CI gate; exits 0 if all manifests current, 1 if any are missing/stale. `src/` stores manifests as sidecars (`*.manifest.json`), so `--manifest-file` is required — without it the check looks for embedded footers and always fails (issue #47).

## Tool CLI Signatures
- `gherkin-parser`: requires two args: `gherkin-parser <feature-file> <json-output>`; bare `gherkin-parser <file>` fails with usage error; call WITHOUT `rtk` prefix — rtk breaks it
- `gherkin-mutator`: requires `--feature <feature-file>`, `--generated-dir <dir>`, and `--runner-worker <path>`; no `--help` flag; use `--workers 4` (runner_adapter.py is now concurrent)
- `generate_acceptance.py`: pass just `module_name` (e.g. `run_loop_steps`), NOT `acceptance.steps.module_name` — the generator adds the prefix automatically
- `mutate4py --scan`: accepts exactly ONE file argument; loop over files separately for multi-file scans

## Acceptance Test Safety
- Committed fixtures in `acceptance/fixtures/` (`plain.py`, `stale.py` for `manifest.feature`; `mixed_operators.py` and the others for `site-discovery.feature`) are committed inputs and MUST NOT be overwritten; steps that run mutate4py against one work on a writable copy (see `acceptance/steps/manifest_steps.py:setup_copy()` and `site_discovery_steps.py:given_fixture_copy()`). There is no separate QA feature pass: each `X_qa.feature` was folded into `X.feature`.
- `runner_adapter.py` must be executable (`chmod +x`) before gherkin-mutator can use it; tool does not emit a clear permission error; supports `RUNNER_WORKERS` env var (default 4) for concurrent job execution
- When modifying source with an embedded manifest, always strip manifest first, modify body, then re-embed; never append after the manifest footer — `strip_manifest` removes everything from begin-marker to EOF

## Module Dependency Invariants
- `tach.toml` holds package layering for `src/mutate4py/*` — the rules and the reasoning both. `tach check` enforces it inside the `lint` gate. Read its header before moving a module between layers or adding a `depends_on`.
- Acceptance step files are boundary files (15-site mutation threshold); extractable pure logic belongs in `*_helpers.py` modules with their own unit tests.
- `coverage_helpers.py` is the testable module for acceptance step helper functions; unit tests live in `tests/test_coverage_helpers.py`.
- `cli_surface_helpers.py` is the testable module for CLI surface acceptance step helpers; unit tests live in `tests/test_cli_surface_helpers.py`.
- `run_loop_helpers.py` and `parallel_workers_helpers.py` are the testable modules for the run-loop and parallel-workers acceptance steps; unit tests live in `tests/test_run_loop_helpers.py` and `tests/test_parallel_workers_helpers.py`.
- `__main__.py` is a pure CLI adapter. `_runner.py` re-exports `scan_report` (defined in `_report.py`), `update_manifest` and `check_manifest` (defined in `_manifest_modes.py`); test them directly. Do not move domain functions back to `__main__.py`.

## References
- `CONTEXT.md` — the project's glossary. Use its terms; don't drift to synonyms.
- `docs/adr/` — decisions and their **rejected** alternatives. Read the ADR covering
  an area before changing it: each one exists to stop a deliberate choice being
  "fixed" back. Behaviour itself is documented by the code, not by these.
- Sibling repos (`~/workspace/addi/`): `crap4py` (Python gold template for CI,
  release, `features/*.feature`, `acceptance/`), `mutate4js` (module-for-module
  mirror of this tool), `drywall` (DRY gate binary).
- See `.agents/roles/` for per-role operational rules.
- See `.agents/references/` for deep-dive topics.
- See `.agents/backlog.md` for pending enforcement-gate proposals.
- Role files present: `hardender.md`, `coder.md`, `cleaner.md`, `QA.md`
- `.agents/references/equivalent-mutants.md` — recognized equivalent mutant categories for this project (hardender: no tests needed for these)
