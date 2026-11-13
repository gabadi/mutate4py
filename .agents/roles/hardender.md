# Hardender Role — Operational Knowledge

## Mutation Tool for This Project
This project (mutate4py) is self-hosted — it generates and checks its own mutation manifests. Use `uv run mutate4py` (not `uvx mutate4py`; uvx isolates the env and breaks self-referential scanning).

Key commands:
- `uv run mutate4py src/ --check-manifest --manifest-file` — verify the manifests are current: unit hashes, recorded Survivors and equivalent markers. It runs no test, so it does not check tests digests. CI gate; exits 0 if current, 1 if a manifest is missing, stale, or records an unaccepted Survivor.
- `uv run mutate4py <file> --scan` — scan a single file and print surviving mutants
- `uv run mutate4py <file> --update-manifest` — regenerate and embed a file's manifest

`--scan`, `--update-manifest`, and `--check-manifest` are mutually exclusive. `--scan` and `--update-manifest` accept exactly ONE file; for multi-file operations loop over files or use a directory with `--check-manifest`.

## Running a Scored Mutation Pass (use `just mutate`, never raw `mutate4py --mutate-all`)
`_runner.py` prints one `[i/total] <status> line N ...` line per mutation site unconditionally on a scored run. On a full-src/ run that is many thousands of characters an agent's Bash tool would otherwise capture in full, every hardening iteration.

Invoke scored runs through the justfile instead of calling `mutate4py` directly:
```
just mutate <path>                      # e.g. just mutate src/mutate4py/_runner.py
```
`just mutate` is `justfile`'s wrapper: it redirects the run to a temp log, then prints only the `Mutation Report` block (Killed/Survived/Uncovered counts + every Survivor's `line N desc` — still fully actionable) via `awk '/^Mutation Report$/,0'`. On a non-zero exit other than 3 it also tails the last 20 log lines, so an infra failure that happens before the summary prints is still visible.

Exit 3 means unaccepted Survivors: kill them with a unit test (ADR 0023: code mutation is unit-only, so a Mutant that only a component test kills stays a Survivor), or mark a recognized equivalent with `# mutate4py: equivalent <category>` on the Site's line (ADR 0026). A Survivor recorded on a function whose Unit hash and tests digest are unchanged is skipped by later runs and still exits 3 (ADR 0029). It is not retried, so it has to be killed or accepted rather than waited out.

The loop: a scored run re-scores the changed functions only. A changed function is one whose Unit hash or Tests digest moved since its Manifest entry was written, one that is Unscored, or one that records Survivors but has no digest yet. Each run takes one Measurement first (the unit tests, once, under coverage) and narrows each Mutant to the tests that reached its line, so there is no setup step to run before `just mutate`. An unchanged function is skipped, its recorded Survivors included, and they still fail the run. Pass `--mutate-all` (`just mutate <path> --mutate-all`) only for a deliberate full re-score.

`just check` (no args) runs the full CI-equivalent gate list the same way — one ✓/✗ line per gate, full output in `check.log`, tailed only on failure.

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
