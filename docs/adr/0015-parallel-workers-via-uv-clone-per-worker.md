# Parallel workers use clone-per-worker, because PEP 660 breaks the upstream model

Each Worker is a tree copy of the project with its own `uv` venv, under `.mutate4py/workers/`.

## Considered Options

- **mutate4go's model: copy the tree and run the tests with `cwd` set to the copy.** A PEP 660 editable install pins an absolute path to the original source, and `cwd` or `sys.path` cannot redirect it (mutmut v3 #456).
- **Bytecode spoof (mutatest): write the Mutant as `__pycache__` bytecode with a spoofed mtime.** It is a different mutation engine. It discards the byte-offset splice and restore, and its crash safety.
- **A `git clone` per Worker.** It needs a git repository and misses uncommitted edits.
- **Start each Worker through `uv run`.** It prescribes the runner and wraps it two times.
- **Continue when a Worker fails.** The result is not deterministic and reports too few Survivors. A Worker failure fails the run, with no Mutation Report.
