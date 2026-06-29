# Hardender Role — Operational Knowledge

## Mutation Tool for This Project
This project (mutate4py) IS the Python mutation tool. Do not attempt to run mutate4py on itself. Use `mutmut` on this project's own test suite instead.

## CRAP Tool
crap4py is installed from local sibling `~/workspace/addi/crap4py` via `uv tool install ~/workspace/addi/crap4py`, not from PyPI or GitHub URL.

## mutmut Parallelism Flag
mutmut 3.x uses `--max-children` (not `--max-workers`). Use `mutmut run --max-children 8`.

## merge_and_process Directive
`merge_and_process <role> <commit>` in a handoff payload is NOT a script on PATH. It means: run `git merge <commit>` in the hardender worktree, then execute the standard hardening sequence (unit → acceptance → property tests → mutmut → Gherkin mutation → CRAP → DRY).

## mutmut CLI Syntax
`mutmut run` takes mutant-name PATTERNS, not file paths. Use bare `mutmut run` to run all mutants. Use `mutmut run <pattern>` to run matching mutant names. Never pass a file path as the first positional argument.

## mutmut Module-Path Filtering
mutmut v3 does not support module-path filtering (e.g., `mutmut run "mutate4py._runner"` fails with AssertionError) and individual-name filtering also fails if mutants haven't been run yet. Always run `mutmut run --max-children 8` first (no filter) to populate stats, then re-run subsets if needed.

## gherkin-mutator Named Arguments
gherkin-mutator uses `--feature <path>` (named option), not a positional argument. Check `/tmp/aps-build/bb/src/aps/cli/gherkin_mutator.clj` source if CLI is unclear.

## Restoring Files After Manual Mutant Application
After `mutmut apply <mutant>` for debugging, restore with `git checkout <file>` ONLY if no other local changes exist in that file. If you have local edits (e.g. a DRY fix, refactor), first save them: `git stash` (or `git diff > patch.diff && git checkout <file> && git apply patch.diff`). `git checkout <file>` discards ALL unstaged and staged changes, not just the mutant.

## Regenerate Acceptance Entrypoints After Step Handler Changes
After modifying any acceptance step handler file (`*_steps.py`), regenerate the acceptance entrypoints via `gherkin-parser` + `generate_acceptance.py` BEFORE running `gherkin-mutator`. Stale generated entrypoints cause all 19+ mutations to error.

## gherkin-mutator --workers Concurrency Constraint
`gherkin-mutator --workers N` requires a runner-worker safe for concurrent stdin/stdout access. The current `runner_adapter.py` is a single-process server — concurrent requests corrupt its JSON protocol. Always use `--workers 1` (the default). Do not increase workers unless the runner_adapter is redesigned for concurrency.

## Equivalent Mutant Categories (Python)
See `.agents/references/equivalent-mutants.md` for recognized equivalent mutant patterns that do not need test coverage.
