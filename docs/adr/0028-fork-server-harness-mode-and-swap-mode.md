# Fork server, harness mode and swap mode in the forking executor

A forking run primes the `ForkingExecutor` in a fork server and forks one child for each Mutant. For each guarded file, the child imports it fresh, swaps in the changed bodies, or runs a fresh interpreter (harness).

## Considered Options

- **Swap in a child forked from the orchestrator.** Self-hosting children inherit caches and logging set-up that the Measurement did not see, and a swap into `_forking_executor.py` can change the exit status of the child.
- **The orchestrator child plus a "fork baseline"** (run the clean suite one time in a forked child and distrust the failing tests). It catches clean-state failures, not a Mutant that fails only against clean-built state, and it costs a full suite run.
- **A third `SwapExecutor` chosen by `_executor_selection`.** Selection occurs one time at prime, but the safety of a swap is decided for each Mutant.
- **Always `execv` in the child.** That is the subprocess cost that the fork server removes.
- **`importlib.reload` in the child.** Other modules keep references to the old function and class objects, so the tests would run stale code.
