# mutate4py — context & glossary

A faithful Python port of `unclebob/mutate4go`, cross-checked against
`unclebob/clj-mutate`, mirroring `gabadi/mutate4js` module-for-module. The
authoritative behavior spec is [`docs/spec.md`](docs/spec.md); the feature roadmap
is [`docs/plan.md`](docs/plan.md); decisions are in [`docs/adr/`](docs/adr/).

## Before exploring, read these

- `docs/spec.md` — the faithful-port contract ([PORT] vs [PY] tagged).
- `docs/plan.md` — feature decomposition and order.
- `docs/adr/` — read the ADRs touching the area you are about to work in.

Use the glossary terms below in issue titles, test names, and proposals; don't
drift to synonyms. If a concept you need isn't here, that's a signal — either
you're inventing language the project doesn't use, or there's a real gap to record.
If your output contradicts an ADR, surface it explicitly rather than overriding it.

## Glossary

The project's ubiquitous language, organized by the feature that introduces each
term. This is the single canonical glossary for the project.

### Site discovery & operators (F1)

- **Site** — a single AST location that can be mutated: one operator, one boolean
  literal, or one integer `0`/`1`. Each site yields exactly one *mutant*. (ADR
  0001.)
- **Mutant** — the mutated form of a site (e.g. `+`→`-`). One operator/literal per
  site, one mutant per site.
- **Operator catalogue** — the locked set of mutations (spec §3, ADR 0001):
  arithmetic, relational, equality/identity/membership *negation flips*, logical,
  boolean, constant. `*`→`/` only.
- **Negation flip** — mutating a comparison to its logical negation (`==`→`!=`,
  `is`→`is not`, `in`→`not in`). The Python localization of mutate4go's equality
  category; never a cross-coercion-family swap.
- **Function unit** (a.k.a. *unit*) — the granularity the manifest tracks and
  differential reruns scope by. `func/foo` for a top-level `def`/`async def`,
  `func/Class.m` for a method. Nested `def`/`lambda` and decorators **fold into**
  the enclosing named unit (NOT separate units — deliberately the opposite of
  crap4py's per-function scoring; ADR 0001). Module-level sites have an **empty
  FunctionID** and are still mutated.
- **FunctionID** — the unit id attributed to a site by line range; empty for
  module-level sites.
- **Index** — a site's stable position after sorting all sites by `(line, column)`.
- **Splice / restore** — applying a mutant by byte-offset source edit and rewriting
  the original back. The in-place model (one file on disk → one mutant at a time),
  editable-install-proof. Serial on the F4 path; F6 runs N isolated copies in
  parallel (spec §9, reopened — ADR 0015).
- **`--scan`** — read-only CLI mode printing site *counts* only (no coverage, no
  tests, no write, no per-site listing; ADR 0001, 0002).

### Manifest (F2)

- **Manifest** — a single JSON object embedded in a source file's footer between
  `# mutate4py-manifest-begin/-end`, recording per function unit the structural hash
  at the time it was last mutation-tested; lets a later run tell which units changed.
  Fields: `version`, `tested_at`, `module_hash`, `functions[]` (spec §5). Owned by
  F2; **absent in F1** (ADR 0002).
- **Unit hash** — `sha256(ast.dump(subtree))` of the unit's AST node. Position- and
  reformat-independent; changes on rename/literal/operator/re-block edits (ADR 0005).
- **`module_hash`** — `sha256(ast.dump(module))` over the manifest-stripped source.
  A top-level manifest field, separate from per-unit hashes.
- **Embed** — write the manifest into the footer: strip any existing manifest, trim
  trailing newlines, append `\n\n` + begin marker + `\n# ` + JSON + `\n` + end
  marker + `\n`.
- **Extract** — read a manifest back: locate the markers, strip `# ` prefixes,
  JSON-parse. Missing markers or a parse failure ⇒ "no manifest" (not an error).
- **Strip** — remove a manifest footer, returning the source body up to (and one
  trailing newline after) the begin marker. No marker ⇒ source unchanged.
- **Changed function IDs** — the diff output: ids whose hash differs from the
  previous manifest, plus **new** ids (no previous entry). **Removed** ids are
  dropped. No previous manifest ⇒ all current ids changed.
- **`tested_at`** — RFC3339 timestamp stamped into the manifest when it is
  (re)embedded. Bumped only when the manifest actually changes (ADR 0006,
  extended to the F4 run loop's `_finalize_source` by ADR 0016).
- **`--update-manifest`** — the thin CLI mode that rewrites the footer without
  running mutations. Idempotent: prints `Updated manifest: <file>` when it writes,
  `Manifest unchanged: <file>` when the file already matches (ADR 0006).
- **Differential rerun** — re-testing only sites whose function unit changed since
  the last manifest; the default once a manifest exists (spec §7).

### Coverage (F3)

- **Coverage gate** — the line-coverage filter that partitions F1's discovered sites
  into `covered` / `uncovered`. **Covered** iff the line has an LCOV
  `DA:<line>,<count>` with `count > 0`; absent line or `count == 0` ⇒ **uncovered**.
  Branch (`BRDA`) data is ignored on purpose (ADR 0007).
- **`covered` / `uncovered`** — the two disjoint, exhaustive partitions of the
  discovered sites. `covered + uncovered == total`; each keeps its stable F1 index.
- **`DA` record** — an LCOV line record `DA:<line>,<count>`; the only coverage signal
  the gate reads. `count > 0` means the line executed.
- **`BRDA` record** — an LCOV branch record. Read-and-discarded; never affects the
  gate, so boundary survivors (`>` vs `>=`) are not suppressed.
- **`SF` suffix match** — reconciling an LCOV `SF:<path>` record with the target by
  path suffix (one path is a suffix of the other), bridging absolute-vs-relative
  forms. Ports mutate4go's matching.
- **Coverage acquisition** — obtaining the LCOV via exactly one of three
  mutually-exclusive modes (ADR 0008): **`--cov-cmd <CMD>`** (run **once**, must emit
  LCOV), **`--lcov <PATH>`** (a pre-generated file), **`--reuse-coverage`** (read the
  default path **`coverage.lcov`**; missing file ⇒ hard usage error, ADR 0007).

### Run loop & report (F4)

- **Run loop** — the full mutation run (spec §7): strip manifest → discover →
  build+diff manifest → acquire coverage + partition → select → header → [uncovered
  block] → baseline → per-site apply/test/classify/restore → restore → report →
  re-embed manifest (idempotent under structural equality, ADR 0016) →
  cleanup (ADR 0010).
- **Baseline** — one run of `--test-command` (default `pytest`) on the **unmutated**
  source; it must pass, and its duration sets the mutant timeout.
- **Mutant timeout** — `max(1s, timeout-factor × baseline-duration)`; the `1s` floor
  is fixed.
- **Classification** — the per-site verdict: **killed** (non-zero exit), **timeout**
  (exceeded the mutant timeout, folds into Killed in the report), **survived** (zero
  exit) (ADR 0011).
- **Selected sites** — the covered sites actually mutated, after dropping those not
  in `--lines` and, when differential, those whose FunctionID is unchanged.
  `selected ⊆ covered ⊆ total`.
- **`effectiveSinceLastRun`** — the differential switch: `--since-last-run OR
  (manifest exists AND not --mutate-all AND not --lines)`. Differential is the
  default once a manifest exists; it suppresses the uncovered block.
- **Run header / Mutation Report / Per-mutant progress line** — the §8 output blocks.
  On the **serial** path there is no `Mutation workers:` line and no `worker-<k>`
  token (ADR 0012); both appear only on the **parallel** path (F6, see below).
- **`.mutate4py.bak`** — crash-safety backup of the stripped source, written before
  the per-site loop and removed after. A pre-existing `.bak` is restored at the start
  of the next run, printing `Restored source from backup (previous run was
  interrupted).`
- **Stale-coverage warning** — `Reusing existing coverage; covered/uncovered
  classification may be stale.`, printed on the `--reuse-coverage` run path before the
  header (ADR 0010).

### CLI surface & validation (F5)

- **Flag matrix** — the full §2 option set F5 parses and validates: `--scan`,
  `--update-manifest`, `--lines`, `--since-last-run`, `--mutate-all`,
  `--mutation-warning N`, `--timeout-factor N`, `--test-command CMD`,
  `--max-workers N`, the three coverage flags, `--verbose`, `--help`.
- **Usage error** — a rejected invocation: print a usage/error message, exit
  **non-zero**, run no analysis and no test command. Triggers: unknown flag, missing
  value, invalid numeric value, illegal flag combination, missing/nonexistent source
  file (ADR 0014).
- **Mutual exclusion** — fail-loud rules that reject combined flags rather than
  silently pick a winner (ADR 0008, 0014): `--scan`/`--update-manifest` exclusive of
  each other and of every execution option; `--since-last-run`/`--mutate-all`/
  `--lines` pairwise exclusive; the three coverage flags pairwise exclusive.
- **Positive-int flag** — `--mutation-warning`, `--timeout-factor`, `--max-workers`:
  each requires an integer `≥ 1`; non-integer or non-positive is a usage error.
  `--lines` takes a comma-separated list under the same rule.
- **Dispatch** — after validation, routing accepted options: `--scan` → F1 scan,
  `--update-manifest` → F2 write, otherwise → the F4 run loop (serial, or the F6
  worker engine when `--max-workers ≥ 2`). F5 routes; it never re-implements a target.

### Parallel workers (F6 — §9 reopened)

- **`--max-workers N`** — the worker-count flag, restored to match upstream (ADR
  0013). Parsed/validated in F5 (positive int; default 0/unset = serial); executed in
  F6. Joins only the scan/update-manifest exclusion — it may combine with selection
  flags.
- **Serial-vs-parallel switch** — ported from upstream `runner.go:319`:
  `--max-workers ≤ 1 OR selected sites ≤ 1` → the F4 serial loop, unchanged;
  `--max-workers ≥ 2 AND sites ≥ 2` → the parallel engine. Parallelism is across the
  **selected sites of the one target file**; `maxWorkers` is clamped to the site
  count (ADR 0015).
- **Worker (clone-per-worker)** — an isolated **tree copy** of the working directory
  with its own `uv`-provisioned venv (`uv venv`/`uv sync`); it mutates its **own** file
  copy, so editable installs resolve to it — the reason mutate4go's tree-copy+`cwd`
  model is replaced. The worker runs the user's `--test-command` **verbatim** with
  `cwd = worker-root` (no `uv pip install -e`, no `uv run` wrapping). Copies live under
  `.mutate4py/workers/run-<pid>-<nanos>/worker-<k>/`, skipping `.git`, `__pycache__`,
  `.venv`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, and the worker dir itself; the
  whole run-root is removed when the run ends (ADR 0015).
- **`Mutation workers: <n>` line** — header line printed whenever `--max-workers > 0`,
  **serial or parallel** (upstream-verbatim, `runner.go:614`); `<n>` is the clamped
  count on the parallel path. So a serial `--max-workers 1` run prints it too. This is
  the one deliberate divergence the F6 grilling settled — ADR 0012 amended, ADR 0015
  resolution 7.
- **`worker-<k>` token** — the per-mutant attribution `[i/total] worker-<k> <status>
  …`, present **only** on the true parallel path (workers ≥ 2 AND sites ≥ 2); upstream's
  token lives only in `runMutationsParallel`, so any serial run (incl. `--max-workers 1`)
  has none (ADR 0015).
- **Arrival-order print / index-sorted aggregation** — per-mutant lines print as each
  worker finishes (indices out of sequence), but results are sorted by stable site
  `Index` before the `Mutation Report` / `Survivors:` block, so the report is
  deterministic regardless of worker timing (upstream `sortResults`, `runner.go:457`).
- **Strict worker failure** — any worker write/restore error, or a collected result
  count != selected-site count, aborts the whole parallel run non-zero with no
  `Mutation Report` (upstream `sendFirstError` / "mutation workers stopped after k/n
  results"). On the parallel path a target file outside the working directory is a hard
  error (`runner.go:365`). `.mutate4py.bak` and manifest re-embed stay at the
  orchestration layer — the original is never mutated in parallel, so there is no
  per-worker `.bak` (ADR 0015).

## Faithful-port tags

- **[PORT]** — reproduce mutate4go's behavior exactly.
- **[PY]** — a deviation forced by Python / its ecosystem, justified in the spec.

## Sibling repos (`~/workspace/addi/`)

- `crap4py` — Python gold template (CI, release, features + `*_qa.feature`,
  `docs/adr`). Pattern source for skeleton/CI/`.gitignore`.
- `mutate4js` — the module-for-module mirror of this tool. Its `docs/adr/`
  pre-resolve several F1 questions; cited where relevant.
- `drywall` — the DRY gate binary (CI downloads its release).
