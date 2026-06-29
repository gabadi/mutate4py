# Hardender Role — Operational Knowledge

## Mutation Tool for This Project
This project (mutate4py) is self-hosted — it generates and checks its own mutation manifests. Use `uv run mutate4py` (not `uvx mutate4py`; uvx isolates the env and breaks self-referential scanning).

Key commands:
- `uv run mutate4py src/ --check-manifest` — verify all manifests are current (CI gate; exits 0 if current, 1 if missing/stale)
- `uv run mutate4py <file> --scan` — scan a single file and print surviving mutants
- `uv run mutate4py <file> --update-manifest` — regenerate and embed a file's manifest

`--scan`, `--update-manifest`, and `--check-manifest` are mutually exclusive. `--scan` and `--update-manifest` accept exactly ONE file; for multi-file operations loop over files or use a directory with `--check-manifest`.

## CRAP Tool
crap4py is installed from local sibling `~/workspace/addi/crap4py` via `uv tool install ~/workspace/addi/crap4py`, not from PyPI or GitHub URL.

## merge_and_process Directive
`merge_and_process <role> <commit>` in a handoff payload is NOT a script on PATH. It means: run `git merge <commit>` in the hardender worktree, then execute the standard hardening sequence (unit → acceptance → property tests → mutation manifest check → Gherkin mutation → CRAP → DRY).

## gherkin-mutator Named Arguments
gherkin-mutator uses `--feature <path>` (named option), not a positional argument. Check `/tmp/aps-build/bb/src/aps/cli/gherkin_mutator.clj` source if CLI is unclear.

## Restoring Files After Manual Mutation Debugging
After manually editing a source file to simulate a mutant for debugging, restore with `git checkout <file>` ONLY if no other local changes exist in that file. If you have local edits (e.g. a DRY fix, refactor), first save them: `git stash` (or `git diff > patch.diff && git checkout <file> && git apply patch.diff`). `git checkout <file>` discards ALL unstaged and staged changes, not just the mutation.

## Regenerate Acceptance Entrypoints After Step Handler Changes
After modifying any acceptance step handler file (`*_steps.py`), regenerate the acceptance entrypoints via `gherkin-parser` + `generate_acceptance.py` BEFORE running `gherkin-mutator`. Stale generated entrypoints cause all 19+ mutations to error.

## gherkin-mutator --workers
`runner_adapter.py` is concurrent (ThreadPoolExecutor, default 4 workers via `RUNNER_WORKERS` env var). Use `--workers 4` with gherkin-mutator. For all features in parallel, use `acceptance/run_gherkin_mutation.sh`.

## Equivalent Mutant Categories (Python)
See `.agents/references/equivalent-mutants.md` for recognized equivalent mutant patterns that do not need test coverage.
