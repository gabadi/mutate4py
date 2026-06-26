# Hardender Role — Operational Knowledge

## Mutation Tool for This Project
This project (mutate4py) IS the Python mutation tool. Do not attempt to run mutate4py on itself. Use `mutmut` on this project's own test suite instead.

## CRAP Tool
crap4py is installed from local sibling `~/workspace/addi/crap4py` via `uv tool install ~/workspace/addi/crap4py`, not from PyPI or GitHub URL.

## mutmut Parallelism Flag
mutmut 3.x uses `--max-children` (not `--max-workers`). Use `mutmut run --max-children 8`.

## merge_and_process Directive
`merge_and_process <role> <commit>` in a handoff payload is NOT a script on PATH. It means: run `git merge <commit>` in the hardender worktree, then execute the standard hardening sequence (unit → acceptance → property tests → mutmut → Gherkin mutation → CRAP → DRY).
