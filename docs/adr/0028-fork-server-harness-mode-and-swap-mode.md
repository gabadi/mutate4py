# Fork server, harness mode and swap mode in the forking executor

**Status:** accepted

The forking executor never runs in the orchestrator. A serial forking run starts
one **fork server**: a `_worker_server` process over the project tree itself (no
clone), under the Project environment, spawned through `WorkerProcessExecutor`,
the adapter parallel Workers already use. The server primes the
`ForkingExecutor` (collect-only against an empty scratch dir, with the run's
`-p no:<name>` blocks) and forks one child per Mutant. The orchestrator has
imported and run nearly every mutate4py module and the Measurement, so keeping
it out keeps its state out of every Mutant.

At prime the executor decides, per guarded file, how each child gets the
mutated code (`file_mode`):

- **fresh import**: the file is not loaded after prime; the child imports it
  fresh from disk, in-process.
- **harness**: the file was loaded before prime, so it is one of the server's
  own modules (the executor and protocol code the child runs around pytest).
  Every Mutant runs in a **fresh interpreter**: a swap would put mutated code
  into the code that reads pytest's result and sets the child's exit status.
- **swap**: prime imported the file (a conftest or a plugin did). Each child
  plans a body swap (`_code_swap.plan_swap`) from the clean source read at prime
  to the file on disk and applies it to the live functions prime's import built
  (`_fork_child.swap_in`), then runs pytest in-process. Live closures made at
  import (a decorator's wrapper) are swapped too.

The swap is refused, and that Mutant alone runs in a fresh interpreter, when the
two code trees cannot be paired, when module-level or class-body code differs (a
decorator, a default argument, an annotation, a module constant, a class
attribute), when a free-variable set changes, when an outermost changed function
has no live object, or when a changed body ran at import. "Ran at import" is the
**import-time execution check**: a body line the Measurement reached under the
Empty context (ADR 0027), sent to the server at launch. State that clean code
built at import could otherwise fail a Mutant a fresh run lets survive.

A fresh interpreter is the forked child `execve`ing `python -m pytest` with
`PYTHONDONTWRITEBYTECODE=1`: same pid, so the parent's wait, timeout kill and
exit-code Classification are unchanged. A swap child reports which path it took
through a pipe the parent reads after the child ends; an empty report counts as
a fresh interpreter, so a swap is never claimed unseen. The report's `Executor:`
line counts the three separately, e.g.
`Executor: forking (fresh import 0, swap 31, fresh interpreter 4)`.

Live state the clean code computed during a test (a memoised result) can survive
a swap; it can only make a Mutant survive, and Survivor confirmation re-runs
every Survivor through the subprocess executor with the full test set.

The whole run falls back to the subprocess executor only when forking is
impossible or unsafe: no `os.fork`, pytest not importable in the server,
`--no-fork`, or a fork-unsafe plugin (tach) registered by the prime session.
"Module leaked at prime" is no longer a fallback.

## Rejected alternatives

- **A. (chosen)** Prime in a fork server; mode per file at prime; swap per
  Mutant in the child, gated by the shallow comparison and the import-time
  execution check.
- **B. Swap in a child forked from the orchestrator.** Self-hosting children
  inherit caches and logging set-up the Measurement never saw, and a swap into
  `_forking_executor.py` can rewrite the child's own exit status.
- **C. B plus a "fork baseline"** (run the clean suite once in a forked child and
  distrust failing tests). Catches clean-state failures, not a Mutant that fails
  only against clean-built state, and costs a full suite run.
- **D. A third `SwapExecutor` chosen by `_executor_selection`.** Selection
  happens once at prime; whether a swap is safe is decided per Mutant.
- **E. Always `execv` in the child.** That is the subprocess cost this removes.
- **F. `importlib.reload` in the child.** Other modules keep references to the
  old function and class objects, so tests would exercise stale code.
