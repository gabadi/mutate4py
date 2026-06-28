# Parallel `--max-workers` uses `uv`-provisioned clone-per-worker (F6 direction)

**Status:** proposed (F6) · recorded at F5 time because the mechanism choice was
made when §9 was reopened
**Feature:** F6 (parallel-workers) · **Spec:** §9 (to be rewritten in F6)

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

## Open for F6 grilling

- Worker-copy granularity (full git-clone vs minimal tree copy) and the exact `uv`
  provisioning commands.
- Worker output-directory convention (mirror mutate4js `.mutate4js/workers/` →
  `.mutate4py/workers/`?).
- How `.mutate4py.bak` crash-safety composes with per-worker copies.
- Whether `--max-workers 1`/0 stays on the serial F4 path (no provisioning).
- The §9 rewrite ("parallelism via clone-per-worker") and the ADR 0012 amendment
  (restore `Mutation workers:` / `worker-<k>` output for `workers > 1`).

**Considered and rejected:** mechanism 1 (unsound in Python), mechanism 3 (different
engine, would discard the faithful byte-splice port).
