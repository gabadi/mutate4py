# mutate4py — faithful port spec

A Python mutation tester, ported from `unclebob/mutate4go` with the user-facing
contract cross-checked against `unclebob/clj-mutate`. Where two independent ports
(Go + Clojure) agree, that is the **stable contract**; where each localizes, the
divergence is language-specific.

Each item is tagged:

- **[PORT]** — reproduce mutate4go's behavior exactly.
- **[PY]** — deviation forced by Python / the Python ecosystem, with the reason.

The companion to this is the JS sibling spec in `gabadi/mutate4js` (`docs/spec.md`),
which this mirrors module-for-module.

---

## 0. Design decisions locked (the grilling)

| # | Decision | Tag |
|---|----------|-----|
| 1 | Coverage acquisition split into `--lcov` / `--cov-cmd` / `--reuse-coverage` | [PY] |
| 2 | Manifest hash = `ast.dump()` (structural), **not** whitespace-collapse | [PY] |
| 3 | Function unit = top-level `def` / method / `async def`; nested defs & lambdas fold into enclosing named unit | [PORT]+[PY] |
| 4 | Operators = core set + `and`/`or` + `True`/`False` + comparison-negation flips (`==`/`!=`, `is`/`is not`, `in`/`not in`) | [PY] |
| 5 | In-place splice/restore mutation; `--max-workers` **restored** (REOPENED — see §9, ADR 0013/0015): serial by default, parallel via `uv`-provisioned clone-per-worker; mutate4go's tree-copy+`cwd` model replaced as editable-install-unsound | [PY] |
| 6 | `--test-command` defaults to `pytest` | [PY] |

---

## 1. Substrate & distribution **[PY]**

mutate4go is a Go binary. mutate4py cannot be.

- **Language:** Python ≥ 3.10 (matches `crap4py`). **Parser:** stdlib `ast`
  (zero dependencies; `end_lineno`/`end_col_offset` available since 3.8 give the
  byte-precise spans needed for splice/restore).
- **Packaging:** `hatchling` + `pyproject.toml`, console-script entry point
  `mutate4py = "mutate4py.__main__:main"` (mirrors crap4py).
- **Distribution:** **PyPI**. Run with `uvx mutate4py`, install with
  `uv tool install mutate4py`.
- **Reason:** a mutation tool is a per-project dev tool that runs in the project's
  own toolchain; the per-mutant cost is the language-native test run, so a native
  binary buys nothing. (Identical rationale to mutate4js.)

---

## 2. CLI surface

Mutate-test one file at a time: `mutate4py path/to/file.py [options]`

| Flag | mutate4go | mutate4py | Tag |
|------|-----------|-----------|-----|
| `--scan` | count sites, no coverage/tests | same | [PORT] |
| `--update-manifest` | rewrite footer manifest only | same | [PORT] |
| `--lines L1,L2,...` | only these source lines | same | [PORT] |
| `--since-last-run` | only changed functions | same | [PORT] |
| `--mutate-all` | all covered sites despite manifest | same | [PORT] |
| `--mutation-warning N` | warn when sites > N (default 50) | same | [PORT] |
| `--timeout-factor N` | mutant timeout = N × baseline (default 10) | same | [PORT] |
| `--verbose` | log actions to stderr | same | [PORT] |
| `--help` | usage and exit | same | [PORT] |
| `--test-command CMD` | default `go test ./...` | default **`pytest`** | [PY] |
| `--cov-cmd CMD` | — (Go appends `-coverprofile`) | command that emits LCOV | [PY] |
| `--lcov PATH` | — (fixed path) | path to LCOV file | [PY] |
| `--reuse-coverage` | reuse coverprofile on disk | reuse LCOV on disk | [PORT]/[PY] |
| `--max-workers N` | N isolated parallel workers | same — serial default, parallel via `uv` clone-per-worker (§9) | [PORT]/[PY] |
| `--manifest-file PATH` | — | store manifests in a shared sidecar JSON file at PATH (keyed by source path) instead of the in-source footer | [PY] |

**[PY] reasons:**

- **`--test-command` defaults to `pytest`** (Go defaults `go test ./...`, clj
  defaults `clj -M:spec ...`; all three ports ship a default — `pytest` is the
  Python near-universal). Override for `unittest`/`nose`/custom.
- **Coverage acquisition split (`--cov-cmd` / `--lcov` / `--reuse-coverage`).**
  mutate4go appends `-coverprofile=...` to the test command; Python has no
  universal coverage flag, so coverage is acquired separately. clj-mutate reads
  LCOV from a fixed path and auto-regenerates; mutate4py follows the mutate4js
  split instead (explicit, no magic path guessing). Generate LCOV with
  `pytest --cov --cov-branch --cov-report=lcov:lcov.info` (coverage.py).
- **`--max-workers` kept (REOPENED — see §9).** Restored to match
  mutate4go/clj-mutate: serial by default, parallel when `N >= 2`. The one
  divergence is the worker-provisioning mechanism — Go/Clojure copy-isolate workers
  via `cwd`, which is unsound under Python editable installs, so mutate4py provisions
  isolated per-worker copies with `uv` instead (clone-per-worker). Parsed/validated in
  F5; executed in F6.
- **`--manifest-file PATH` (opt-in sidecar manifest storage).** Neither mutate4go nor
  clj-mutate has this — Python-only, and additive: default behavior (in-source
  footer) is unchanged when the flag is absent. Motivation: the embedded footer is a
  single unwrappable JSON line with no length cap, which trips line-length lint gates
  (e.g. ruff E501) on any file that has ever been mutation tested, and a hand-added
  `# noqa` on that line does not survive — `embed_manifest()` strips and rewrites the
  footer on every `--update-manifest` / scored run. When `--manifest-file PATH` is
  given, `--check-manifest` and `--update-manifest` read/write the manifest JSON at
  `PATH` instead of the footer, the scored-run finalizer does the same, and the
  source file is left free of any manifest footer (existing footers are stripped on
  the next write). `PATH` holds one shared JSON object keyed by source path (`{source
  path: manifest}`), not a single manifest — so one `PATH` works for a directory
  target too: every file under it reads and writes only its own key, other files'
  entries are left untouched, and no fan-out restriction applies.

**[PORT] mutual-exclusion rules** (reproduce exactly):
- `--scan` and `--update-manifest` are mutually exclusive and cannot combine with
  any execution option (`--lines`, `--since-last-run`, `--mutate-all`,
  `--timeout-factor`, `--test-command`, `--max-workers`).
- `--since-last-run`, `--mutate-all`, `--lines` are pairwise exclusive.
- `--max-workers` joins only the scan/update-manifest exclusion; it may combine with
  the selection flags.
- Numeric flags reject non-positive / non-integer values (incl. `--max-workers`).
- Missing source file → usage error.

---

## 3. Mutation operators **[PY]**

The mutation categories are shared across all ports; each is expressed in the
**target language's native operators** (Uncle Bob's localize-per-language
practice, proven by clj-mutate adding `inc`/`dec`, `=`/`not=`, `if-not`).

**Principle locked in grilling:** *mutate every native comparison operator by
flipping it to its negation; never swap across coercion families.*

| Category | Mutations |
|----------|-----------|
| Arithmetic | `+` → `-`, `-` → `+`, `*` → `/` |
| Comparison (relational) | `>` → `>=`, `>=` → `>`, `<` → `<=`, `<=` → `<` |
| Equality (negation flip) | `==` → `!=`, `!=` → `==` |
| Identity (negation flip) | `is` → `is not`, `is not` → `is` |
| Membership (negation flip) | `in` → `not in`, `not in` → `in` |
| Logical | `and` → `or`, `or` → `and` |
| Boolean | `True` → `False`, `False` → `True` |
| Constant | integer `0` → `1`, `1` → `0` |

- **Identity/membership are the Python localization** of the equality category:
  `if x is None:` / `if x in valid:` are the dominant idiomatic comparisons, so a
  faithful port must mutate them (same reasoning that adds `===`/`!==` to
  mutate4js). They are negation flips, not coercion swaps.
- **No `/` → `*`** (only `*` → `/`). [PORT]
- **Excluded:** augmented-assignment (`+=`/`-=`), unary-removal, and any
  cross-family swap — these are *new categories* no port introduced (unary/null
  were fabrications corrected in the mutate4js spec). Revisit only on field demand.
- One mutant per site; exactly one operator/literal per site.

---

## 4. Site discovery & function attribution

- **[PORT]** Walk the whole file's AST; every operator / boolean / integer `0`/`1`
  literal is a site. Sort sites by (line, column); assign a stable `Index`.
- **[PORT]** Each site is attributed to its enclosing function by line range; sites
  outside any function get an empty FunctionID and are still mutated (module-level
  code is NOT skipped).
- **[PY] function unit definition.** The manifest unit:
  - top-level `def foo` → `func/foo`
  - `async def foo` → `func/foo` (same as sync)
  - method (`def m` inside a class) → `func/Class.m`
  - nested `def` and `lambda` are **not** separate units; their sites attribute to
    the enclosing named unit by line range (mirrors mutate4go's
    `functionIDAtLine` and clj's "top-level forms").
  - decorators do not create units; the decorated `def` is the unit.
- **[PORT]** Apply = source splice by offset, restore = rewrite original. Python
  `ast` column offsets are UTF-8 byte offsets within a line — compute absolute
  byte offsets from `(lineno, col_offset)` / `(end_lineno, end_col_offset)` over
  the file's line index.

---

## 5. Manifest **[PY] on the hash, [PORT] on the format**

Single JSON object embedded in the file footer between `#`-comment markers:

```python
# mutate4py-manifest-begin
# {"version":1,"tested_at":"2026-06-24T...","module_hash":"<sha256>","functions":[{"id":"func/foo","name":"foo","line":5,"end_line":25,"hash":"<sha256>"}]}
# mutate4py-manifest-end
```

- **Hash = SHA-256** of the unit (matches mutate4go).
- **[PY] Normalization = `ast.dump()` of the unit's parsed subtree**, *not*
  whitespace-collapse. Python whitespace is syntactically significant
  (indentation = block structure); `text.split().join(" ")` would make a re-indent
  that moves a line in/out of a block hash identically. `ast.dump()` is
  structure-based: immune to reformatting and comment edits, changes on any
  behavior-affecting edit (rename, number change, re-block). This is a deliberate
  divergence from mutate4go's "any textual edit re-tests" contract, accepted for
  Python correctness.
- `module_hash` = SHA-256 of `ast.dump()` of the whole manifest-stripped module.
- Per function: `id, name, line, end_line, hash`.
- `tested_at` = full RFC3339 timestamp.
- **Embed:** strip any existing manifest, trim trailing newlines, append
  `\n\n` + begin marker + `\n# ` + JSON + `\n` + end marker + `\n`. [PORT]
- **Extract:** find markers, strip `# ` prefixes, JSON-parse. [PORT]

**[PY] Sidecar storage (`--manifest-file PATH`, opt-in).** Same per-file JSON
schema, wrapped one level: `PATH` holds a single JSON object mapping source path
→ manifest (`{"a.py": {...}, "b.py": {...}}`), pretty-printed (`indent=2`,
trailing newline).

- `write_sidecar_manifest(manifest_path, source_path, manifest)` reads the whole
  map at `manifest_path` (missing/unparseable ⇒ `{}`), sets
  `map[source_path] = manifest`, and rewrites the whole file — other source
  paths' entries are read back unchanged and rewritten verbatim, so one `PATH`
  safely accumulates entries across many files (e.g. a directory run).
- `read_sidecar_manifest(manifest_path, source_path)` reads the map and returns
  `map[source_path]`; missing file, parse failure, or a missing key for
  `source_path` all collapse to `(None, False)` — same "no manifest, not an
  error" contract as `extract_manifest`.
- The source file is written manifest-stripped (`strip_manifest()` output, no
  footer) whenever it is written at all — `update_manifest` and the scored-run
  finalizer both apply this in sidecar mode, so switching a file from embedded to
  sidecar storage strips its old footer on the first write.
- Hashing is identical either way: `build_manifest()` always operates on
  manifest-stripped source, so relocating storage does not touch mutation-testing
  correctness (module_hash, per-function hashes, diffing) at all.
- `--check-manifest` / `--update-manifest` / the scored-run finalizer all read a
  file's prior manifest from its own key in `PATH` when `--manifest-file` is
  given, and from the in-source footer otherwise — never both. A stray footer
  left over from a prior embedded run does not satisfy a sidecar-mode check.
- Directory targets are supported: each file under the directory reads/writes
  only its own key in the shared `PATH`, so a single `--manifest-file PATH`
  covers a whole `--update-manifest`/`--check-manifest` sweep.

---

## 6. Coverage

- **[PY] format: LCOV** (clj-mutate already reads LCOV — it is the cross-language
  coverage substrate; coverage.py emits it). Reuse crap4py's LCOV parser and
  suffix-based path matching.
- **[PORT] gate = line coverage.** A site is eligible iff its line has an LCOV
  `DA:<line>,<count>` with `count > 0`. **Branch (`BRDA`) data is ignored** —
  matching mutate4go; branch-gating would suppress the boundary survivors the tool
  exists to find.
- **[PORT] partition:** sites split into `covered` / `uncovered` by that gate.
- **[PY] acquisition:** run `--cov-cmd` once (must emit LCOV), or read `--lcov PATH`,
  or `--reuse-coverage` from a default path. `--reuse-coverage` with no file
  present → hard error (matches mutate4go).
- **Open:** default LCOV path for `--reuse-coverage` / `--cov-cmd` output discovery
  (`lcov.info` at repo root is the crap4py/coverage.py convention — confirm).

---

## 7. Run loop **[PORT]**

1. Strip manifest from source, write the stripped file (analysis content).
2. Discover sites + functions; build current manifest; diff vs previous manifest
   → `changed` function IDs.
3. Acquire coverage (§6); partition covered/uncovered.
4. `effectiveSinceLastRun = --since-last-run OR (manifest exists AND not
   --mutate-all AND not --lines)` — differential is the default once a manifest
   exists.
5. `selectSites`: from covered sites, drop those not in `--lines` (if set) and,
   when differential, drop those whose FunctionID is unchanged.
6. Print header (§8); print uncovered list when not differential and no `--lines`.
7. **Baseline:** run `--test-command` once with no mutation; it must pass, and its
   duration sets `timeout = max(1s, timeout-factor × baseline)`.
8. Save `.mutate4py.bak`; for each selected site: apply mutant → write file → run
   test command with timeout → classify → restore original. Statuses:
   non-zero exit → **killed**; timeout → **timeout** (counted as killed); zero exit
   → **survived**.
9. Restore original, print report (§8), embed fresh manifest, cleanup backup.

**[PORT] crash safety:** on the next run, if a `.bak` exists (previous run
interrupted), restore it first and print
`Restored source from backup (previous run was interrupted).`

---

## 8. Output format **[PORT]** (reproduce strings verbatim, minus worker tokens)

**Header:**
```
Mutation run: <file>
Total mutation sites: <n>
Covered mutation sites: <n>
Uncovered mutation sites: <n>
Changed mutation sites: <n>
Manifest exists: <true|false>
Selected mutation sites: <n>
```
Plus `Warning: <n> mutation sites exceeds threshold <m>.` when over warning.
The `Mutation workers: <n>` line is **removed** ([PY] §9).

**Uncovered block** (only when not differential and no `--lines`):
```
Uncovered mutations:
  line <L> <desc> <functionID>
```

**Per-mutant progress:** `[i/total] <status> line <L> <desc> <functionID>`.
The `worker-<k>` token is **removed** ([PY] §9).

**Final report:**
```

Mutation Report
===============
Killed: <killed+timeout>
Survived: <survived>
Uncovered: <uncovered>

Survivors:
  line <L> <desc> <functionID>
```
(Survivors block only when survived > 0.) `<desc>` = `"<original> -> <mutant>"`.

**`--scan` output:**
```
Mutation scan: <file>
Total mutation sites: <n>
Changed mutation sites: <n>
Manifest exists: <true|false>
```
(+ warning line if over threshold). `--update-manifest` prints
`Updated manifest: <file>`.

---

## 9. Parallelism — **[PY] clone-per-worker** (REOPENED; see ADR 0013/0015)

`--max-workers` is a real flag, matching upstream mutate4go: **serial by default**
(`--max-workers <= 1` or a single site), **parallel across the target file's sites**
otherwise. The divergence is the *worker-provisioning mechanism*, because
mutate4go's own model does not survive Python's import system.

**Why mutate4go's mechanism can't be ported verbatim.** mutate4go and clj-mutate
copy the project tree per worker and run each worker's test command with
`cwd = workerRoot`. **This `cwd`-redirect model is unsound in Python.** Confirmed by
research across the Python mutation ecosystem:

- mutate4go's primitive is "splice the mutant into the source file on disk, run
  tests, restore" = **in-place mutation** (mutmut-v2's model). On a *single* copy it
  is **editable-install-proof by construction** (the mutated file *is* the file the
  importer resolves to).
- Every Python tool that parallelized by **copying files** and trusting `cwd` /
  `sys.path` to redirect imports **broke** under `pip install -e .`: PEP 660 editable
  finders write an **absolute** path to the original source, which no cwd-change or
  temp-dir copy overrides (mutmut v3, issue #456 — "could not find any test case for
  any mutant"). So mutate4go's `copyProject` + `cwd = workerRoot` cannot be ported as-is.
- The Python approaches that parallelize *and* survive editable installs each give a
  worker its **own fully-resolved environment**: cosmic-ray git-clones + installs per
  worker; mutatest spoofs `__pycache__` bytecode; pytest-gremlins instruments once +
  env-toggles.

**Decision (reopened).** Keep mutate4go's in-place splice/restore *primitive*, but
run it on a **per-worker isolated copy** whose editable install resolves to *that
copy* — so each worker is editable-proof in its own right. Provision copies with
**`uv`** (near-instant venvs + hardlinked installs from a shared cache), which
removes the per-worker `git clone` + full `pip install` cost that made
clone-per-worker look expensive. This is the cosmic-ray shape, made cheap by `uv`,
and it preserves the byte-splice engine (so no `__pycache__`-spoof rework).

- **Serial path** (`--max-workers <= 1` OR one selected site): the exact in-place
  splice/restore loop, no worker tree, no `worker-<k>` token (this is what F4 shipped;
  ADR 0012). It **does** print the `Mutation workers: <n>` header line whenever
  `--max-workers > 0` — see the output-token rule below.
- **Parallel path** (`--max-workers >= 2` AND >= 2 sites): N `uv`-provisioned worker
  copies, sites fanned across them, results aggregated into the one §8 report; the
  `worker-<k>` progress token appears on every per-mutant line. `maxWorkers` is
  clamped to the site count, and the `Mutation workers: <n>` line shows that clamped
  count.

**Worker provisioning (F6 grilling, ADR 0015).** Each worker is a **tree copy** of the
working directory (skipping `.git`, `__pycache__`, `.venv`, `.pytest_cache`,
`.mypy_cache`, `.ruff_cache`, and the worker dir itself) under
`.mutate4py/workers/run-<pid>-<nanos>/worker-<k>/`, provisioned with `uv venv`/`uv
sync` so the worker has its own resolved environment. The worker then runs the user's
`--test-command` **verbatim** with `cwd = worker-root` (upstream's `cwd = workerRoot`
model) — **no `uv pip install -e`, no `uv run` wrapping** — and the worker's own venv
makes imports resolve to its copy, so each worker is editable-install-proof. The whole
`run-<pid>-<nanos>` root is removed at the end of the run.

**Output-token rule (the one deliberate divergence — upstream-verbatim header, parallel-only
token).** `Mutation workers: <n>` prints whenever `--max-workers > 0` (serial *or*
parallel), matching upstream `runner.go:614`; the `worker-<k>` per-mutant token appears
**only** on the true parallel path (workers ≥ 2 AND sites ≥ 2), because upstream's token
lives only in `runMutationsParallel`. So a serial `--max-workers 1` run prints
`Mutation workers: 1` with untagged per-mutant lines. Per-mutant lines print in
**arrival order** (workers finish out of sequence), but results are **sorted by stable
site index** before the `Mutation Report` / `Survivors:` block, so the report is
deterministic.

**Crash-safety & failure (ADR 0015).** `.mutate4py.bak` and the manifest re-embed stay
at the orchestration layer (unchanged from F4): in parallel the **original file is never
mutated** — only worker copies are, each restored after each mutant — so the `.bak` is
pure crash-safety, and there is **no per-worker `.bak`**. On the parallel path a target
file outside the working directory is a hard error (upstream `runner.go:365`). Worker
failure is **strict / all-or-nothing**: any worker write/restore error, or a collected
result count != selected-site count, aborts the run non-zero with no `Mutation Report`.

**Boundary:** F5 parses/validates `--max-workers` and dispatches the count; **F6**
implements the parallel engine and the serial/parallel switch.

---

## 10. Reference CLIs (user-facing details extracted)

### mutate4go
```
mutate4go [--scan] [--update-manifest] [--lines L,...] [--since-last-run]
          [--mutate-all] [--reuse-coverage] [--mutation-warning 50]
          [--timeout-factor 10] [--test-command "go test ./..."]
          [--max-workers 1] [--verbose] path/to/file.go
```
Coverage from Go coverprofile; manifest in file footer; differential-by-default
once manifest exists.

### clj-mutate (`clj -M:mutate` / `bb mutate`)
```
clj -M:mutate [--scan] [--update-manifest] [--lines L,...] [--since-last-run]
              [--mutate-all] [--reuse-lcov] [--mutation-warning 50]
              [--timeout-factor 10] [--max-workers N]
              [--test-command "clj -M:spec --tag ~no-mutate"] path/file.cljc
```
**Reads LCOV** from `target/coverage/lcov.info` (auto-regenerates). Operators
localized: `inc`/`dec`, `=`/`not=`, `if`/`if-not`, `when`/`when-not`. This is the
precedent for localizing the operator set per language.

---

## 11. Build order (follows mutate4go module deps)

mutation discovery → manifest → coverage → runner → CLI validation.
Reuse from siblings: `crap4py` LCOV parser + Python `ast` patterns + packaging;
`gabadi/mutate4js` `docs/spec.md` for module structure and exact output strings.

Checkpoint logs persist to `gabadi/mutate4py-entire` via `entire`.
