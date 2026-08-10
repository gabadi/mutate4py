# Parallel `--max-workers` uses `uv`-provisioned clone-per-worker (F6 direction)

**Status:** accepted (F6) · mechanism recorded at F5 time when §9 was reopened;
grilling open questions resolved in F6 (see "F6 grilling resolutions" below)
**Feature:** F6 (parallel-workers) · **Spec:** §9 (rewritten in F6)
**Amended by:** ADR 0019 (single execution model) — see amendment appended below.

`--max-workers` is restored as a real flag (ADR 0013). The execution it enables is
F6. This ADR records *which* parallel mechanism F6 will use, so the decision is not
lost between features.

## The constraint

Three parallel mechanisms exist in the Python mutation ecosystem:

1. **mutate4go's own model** — copy the project tree per worker, run each worker's
   tests with `cwd = workerRoot`. **Unsound in Python:** PEP 660 editable installs
   pin an absolute path to the original source that `cwd`/`sys.path` cannot redirect
   (mutmut v3 #456). Cannot be ported verbatim.
2. **clone-per-worker (cosmic-ray)** — each worker is a full isolated checkout with
   its own install; it mutates *its own* copy on disk. Editable-install-proof
   because the worker's editable install resolves to the worker's own copy.
3. **bytecode-spoof (mutatest)** — write the mutant as a `__pycache__` bytecode file
   with a spoofed source mtime; no source edits. Editable-proof, but a **different
   mutation engine** than F1's byte-offset splice and F4's `.mutate4py.bak`
   crash-safety — adopting it would mean reworking the core.

## Serial-vs-parallel switch (ported verbatim from upstream)

Upstream `runner.go:319` chooses the path per run:
`if maxWorkers <= 1 || len(sites) <= 1 → serial, else → parallel`. F6 ports this
**exactly**:

- `--max-workers` unset / 0 / 1, **or** a run with ≤ 1 selected site → the **existing
  F4 serial loop**, unchanged (the in-place splice/restore, identical output, no
  worker tokens, ADR 0012 still holds for this path).
- `--max-workers ≥ 2` **and** ≥ 2 selected sites → the new parallel engine.

Parallelism is **across the selected mutation sites of the single target file**, not
across files — upstream mutates one file per invocation and fans its sites out over
`maxWorkers` isolated project copies. `maxWorkers` is clamped to `len(sites)`
(`runner.go:368`).

## Decision

F6 uses **clone-per-worker (mechanism 2), provisioned with `uv`.**

- Keeps F1's byte-offset splice/restore engine intact — each worker runs the *same*
  mutation primitive on its *own* file copy. No bytecode-spoof rework (mechanism 3
  rejected for that reason).
- `uv` is the cost lever that makes clone-per-worker practical. The original §9
  objection to mechanism 2 was the per-worker `git clone` + full `pip install` cost;
  `uv venv` is near-instant and `uv` installs hardlink packages from a shared global
  cache, so per-worker provisioning is close to free.
- Editable-install-proof by construction (each worker's editable install points at
  its own copy), which is exactly what mechanism 1 fails.

## F6 grilling resolutions

The open questions above are resolved as follows (grounded in upstream
`internal/runner/runner.go` and the `mutate4js` sibling unless noted):

1. **Worker-copy granularity & `uv` command.** A **tree copy** (not `git clone`), so
   it works whether or not the target is a git repo and captures uncommitted edits —
   this mirrors upstream `copyProject` (a `filepath.WalkDir` copy, not a clone). Each
   worker copy is then provisioned with **`uv venv` / `uv sync`** so the worker has
   its own resolved environment. **No `uv pip install -e`** and **no wrapping of the
   user's test command in `uv run`**: the worker runs the user's `--test-command`
   *verbatim* with `cwd = worker-root` (upstream's `cwd = workerRoot` model), and the
   worker's own provisioned venv + `uv`'s project discovery make imports resolve to
   that worker's copy. This is what makes each worker editable-install-proof.
2. **Worker output directory.** `.mutate4py/workers/run-<pid>-<nanos>/worker-<k>/`,
   mirroring the sibling `.mutate4js/workers/` convention (upstream uses
   `target/mutation-workers/run-<pid>-<nanos>/worker-<i>`; Python has no `target/`).
   The whole `run-<pid>-<nanos>` root is removed when the run ends (upstream
   `defer os.RemoveAll(runRoot)`).
3. **Skip-list (Python port of `shouldSkipCopy`).** Don't copy VCS, caches, or the
   worker dir itself: `.git`, `__pycache__`, `.venv`, `.pytest_cache`, `.mypy_cache`,
   `.ruff_cache`, and `.mutate4py/` (prevents recursive self-copy). Ports upstream's
   intent (`.git`, `.gocache`, `.gomodcache`, `.tools`, `target`) to Python tooling.
4. **`.mutate4py.bak` composition.** **Unchanged from F4 — it stays at the
   orchestration layer, not per worker.** Upstream's caller does
   `SaveBackup → runMutations(serial|parallel) → restore → summarize → embed manifest
   → CleanupBackup`; the parallel branch is interchangeable inside `runMutations`. In
   parallel the **original file is never mutated** (only worker copies are, and each
   worker restores its own copy after each mutant), so the `.bak` is pure crash-safety
   for an interrupted run. **No per-worker `.bak`.**
5. **Serial path for `--max-workers` 0/1.** Yes — `--max-workers <= 1` **or** ≤ 1
   selected site stays on the **F4 serial loop with no worker provisioning at all**
   (no tree copy, no venv). The only serial-output change is the `Mutation workers:`
   header line (resolution 7).
6. **Source-inside-cwd.** Port the upstream hard error (`runner.go:365`): on the
   **parallel path only**, if the target file is not under the working directory, abort
   with a usage/IO error before provisioning any worker. The serial path is unaffected.
7. **`Mutation workers:` / `worker-<k>` output (the one deliberate divergence —
   see ADR 0012 amendment).** Upstream prints `Mutation workers: <n>` whenever
   `MaxWorkers > 0` (`runner.go:614`), *including a serial `--max-workers 1` run*.
   F6 keeps this **upstream-verbatim**: the **`Mutation workers: <n>` header line
   prints whenever `--max-workers > 0`** (serial or parallel; `<n>` is the clamped
   count on the parallel path). The **`worker-<k>` per-mutant token, however, appears
   only on the true parallel path** (workers ≥ 2 AND sites ≥ 2) — because upstream's
   token lives only in `runMutationsParallel`; the serial loop has none. So a serial
   `--max-workers 1` run prints `Mutation workers: 1` *and* untagged per-mutant lines.
8. **Print order vs aggregation order.** Per-mutant lines print in **arrival order**
   (each worker `fmt.Printf`s as it finishes — indices appear out of sequence), but
   the collected results are **sorted by stable `Site.Index`** before the report
   (`sortResults`, `runner.go:457`), so the `Mutation Report` tallies and the
   `Survivors:` block are deterministic regardless of worker timing.
9. **Worker failure is strict / all-or-nothing.** If a worker cannot write or restore
   its copy, or the collected result count != selected-site count, the **whole run
   aborts non-zero with an error and prints no `Mutation Report`** (upstream
   `sendFirstError` + `"mutation workers stopped after k/n results"`). Consistent with
   F4's "fail loudly, never print a misleading report" baseline philosophy.

**Considered and rejected:** mechanism 1 (unsound in Python), mechanism 3 (different
engine, would discard the faithful byte-splice port); `git clone` granularity
(requires a git repo, misses uncommitted edits); wrapping the user command in
`uv run` (prescribes the runner, double-wraps `uv run pytest`); graceful-degrade on
worker failure (non-deterministic, under-reports survivors).

## Amendment (2026-08-10) — re-scoped by ADR 0019

The provisioning mechanism above — tree copy, `uv venv`/`uv sync`, verbatim command
with `cwd = worker-root` — is **unchanged**. It becomes the home for the warm
test-executor too: each Worker now additionally provisions and owns exactly one
executor, primed once, inside its own copy — additive to this ADR's
responsibilities, not a competing mechanism. Full reasoning in ADR 0019.
