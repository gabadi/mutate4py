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
| 5 | In-place serial mutation; **`--max-workers` removed**; no tree-copy, no worker isolation | [PY] |
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
| `--max-workers N` | N isolated parallel workers | **removed** — usage error if passed | [PY] |

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
- **`--max-workers` removed.** The flag exists in mutate4go/clj-mutate only
  because Go/Clojure can copy-isolate workers. Python cannot (see §9). A flag
  that silently no-ops would advertise a capability that does not exist, so it is
  omitted; passing it is a usage error pointing at serial behavior.

**[PORT] mutual-exclusion rules** (reproduce exactly):
- `--scan` and `--update-manifest` are mutually exclusive and cannot combine with
  any execution option (`--lines`, `--since-last-run`, `--mutate-all`,
  `--timeout-factor`, `--test-command`).
- `--since-last-run`, `--mutate-all`, `--lines` are pairwise exclusive.
- Numeric flags reject non-positive / non-integer values.
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

## 9. Parallelism — **[PY] removed**

mutate4go and clj-mutate copy the project tree per worker and run each worker's
test command with `cwd = workerRoot`. **This model is unsound in Python** and is
not ported. Confirmed by research across the Python mutation ecosystem:

- The faithful mutate4go mechanism is "splice the mutant into the source file on
  disk, run tests, restore" = **in-place mutation** = mutmut-v2's model. It is
  **editable-install-proof by construction** (the mutated file *is* the file the
  importer resolves to) but **inherently serial** (one file on disk → one mutant at
  a time).
- Every Python tool that parallelized by **copying files** and trusting `cwd` /
  `sys.path` to redirect imports **broke** under `pip install -e .`: PEP 660
  editable finders write an **absolute** path to the original source, which no
  cwd-change or temp-dir copy overrides (mutmut v3, issue #456 — "could not find
  any test case for any mutant").
- The only Python approaches that parallelize *and* survive editable installs
  abandon source-splice entirely (cosmic-ray: git-clone + `pip install` per worker;
  mutatest: spoof `__pycache__` bytecode + `PYTHONCACHEPREFIX`; pytest-gremlins:
  instrument-once + env-var toggle) — all large divergences from mutate4go.

**Decision:** keep mutate4go's exact in-place splice/restore model → always
correct, editable-proof, identical manifest/coverage/output semantics → therefore
**serial only**. `--max-workers` is removed; passing it is a usage error. A later
clone-per-worker mode can be added if field demand appears, but it is out of scope
for v1.

Because nothing is copied, there is **no worker tree, no skip/ignore list, and no
`node_modules`-equivalent dance** (the one place mutate4js needed real
JS-specific engineering simply does not exist here).

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
