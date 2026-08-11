# Parallel workers use clone-per-worker, because PEP 660 breaks the upstream model

**Status:** accepted · mechanism still current; worker *execution* superseded (below)

Three parallel mechanisms exist in the Python mutation ecosystem:

1. **mutate4go's own** — copy the project tree per worker, run tests with
   `cwd = workerRoot`. **Unsound in Python.** PEP 660 editable installs pin an
   absolute path to the original source that `cwd`/`sys.path` cannot redirect
   (mutmut v3 #456). This is why the upstream model cannot be ported verbatim —
   the single most load-bearing fact in this file.
2. **clone-per-worker (cosmic-ray)** — each worker is an isolated copy with its own
   resolved environment, mutating its *own* file. Editable-install-proof by
   construction.
3. **bytecode-spoof (mutatest)** — write the mutant as `__pycache__` bytecode with a
   spoofed mtime. Editable-proof, but a *different mutation engine*: adopting it
   means discarding the byte-offset splice/restore core and its crash-safety.

**Decision: mechanism 2, provisioned with `uv`.** The original objection to
clone-per-worker was per-worker `git clone` + `pip install` cost; `uv venv` is
near-instant and installs hardlink from a shared cache, which removes it. The
byte-splice engine survives intact.

Worker copies are **tree copies**, not clones, so they work outside a git repo and
capture uncommitted edits. They live under
`.mutate4py/workers/run-<pid>-<nanos>/worker-<k>/`; the whole run root is removed at
the end.

## Superseded: how a worker executes

Resolution 1 of this ADR originally said each worker runs the user's test command
*verbatim* with `cwd = worker-root`, relying on the worker's own venv to resolve
imports. **That is no longer how it works** — each Worker now spawns a persistent
`_worker_server.py` process holding one primed `Executor` and dispatches Mutants to
it over a pipe. The `uv venv`/`uv sync` provisioning above is unchanged; the
per-Mutant execution path is not.

**Rejected:** mechanism 1 (unsound); mechanism 3 (discards the byte-splice engine);
`git clone` granularity (needs a repo, misses uncommitted edits); wrapping the user
command in `uv run` (prescribes the runner, double-wraps); graceful-degrade on
worker failure (non-deterministic, under-reports survivors — failure is strict
all-or-nothing, with no `Mutation Report` printed).
