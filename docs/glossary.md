# mutate4py — Domain Glossary

Ubiquitous language for the port. Terms are introduced as features need them.

## Manifest (F2)

- **Manifest** — a single JSON object embedded in a source file's footer recording,
  per function unit, the structural hash at the time it was last mutation-tested.
  Lets a later run tell which units changed. Fields: `version`, `tested_at`,
  `module_hash`, `functions[]`.
- **Function unit** — the granularity a manifest tracks and a hash covers. Id forms:
  `func/foo` (top-level `def`/`async def`), `func/Class.m` (method). Nested
  `def`/`lambda` and decorators do **not** create units; their sites fold into the
  enclosing named unit. (Defined in F1 §4; F2 adds line/hash records for it.)
- **Unit hash** — `sha256(ast.dump(subtree))` of the unit's AST node. Position- and
  reformat-independent; changes on rename/literal/operator/re-block edits. See
  ADR 0005.
- **`module_hash`** — `sha256(ast.dump(module))` over the manifest-stripped source.
  A top-level manifest field, separate from per-unit hashes.
- **Embed** — write the manifest into the footer: strip any existing manifest, trim
  trailing newlines, append `\n\n` + begin marker + `\n# ` + JSON + `\n` + end
  marker + `\n`.
- **Extract** — read a manifest back: locate the markers, strip `# ` prefixes,
  JSON-parse. Missing markers or a parse failure ⇒ "no manifest" (not an error).
- **Strip** — remove a manifest footer, returning the source body up to (and one
  trailing newline after) the begin marker. No marker ⇒ source unchanged.
- **Manifest markers** — `# mutate4py-manifest-begin` / `# mutate4py-manifest-end`,
  the comment lines bounding the embedded footer.
- **Changed function IDs** — the diff output: ids whose hash differs from the
  previous manifest, plus **new** ids (no previous entry). **Removed** ids (in
  previous, absent now) are dropped. No previous manifest ⇒ all current ids changed.
- **`tested_at`** — RFC3339 timestamp stamped into the manifest when it is (re)embedded.
  Bumped only when the manifest actually changes (ADR 0006).
- **`--update-manifest`** — the thin CLI mode that rewrites the footer without
  running mutations. Idempotent: prints `Updated manifest: <file>` when it writes,
  `Manifest unchanged: <file>` when the file already matches (ADR 0006).

## Coverage (F3)

- **Coverage gate** — the line-coverage filter that partitions F1's discovered
  mutation sites into `covered` and `uncovered`. A site is **covered** iff its line has
  an LCOV `DA:<line>,<count>` record with `count > 0`; absent line or `count == 0` ⇒
  **uncovered**. Branch (`BRDA`) data is ignored on purpose (ADR 0007).
- **`covered` / `uncovered`** — the two disjoint, exhaustive partitions of the
  discovered sites. `covered + uncovered == total`; each site keeps its stable F1 index.
- **`DA` record** — an LCOV line record `DA:<line>,<count>`; the only coverage signal
  the gate reads. `count > 0` means the line executed.
- **`BRDA` record** — an LCOV branch record. Read-and-discarded (or never parsed);
  never affects the gate, so boundary survivors (`>` vs `>=`) are not suppressed.
- **`SF` suffix match** — reconciling an LCOV `SF:<path>` record with the target source
  file by path suffix (one path is a path-suffix of the other), bridging
  absolute-vs-relative path forms. Ports `mutate4go`'s matching.
- **Coverage acquisition** — obtaining the LCOV for a run via exactly one of three
  mutually-exclusive modes (ADR 0008):
  - **`--cov-cmd <CMD>`** — run the command **once** (never per site); it must emit LCOV.
  - **`--lcov <PATH>`** — read a pre-generated LCOV file at `PATH`.
  - **`--reuse-coverage`** — read LCOV from the default path **`coverage.lcov`** (the
    coverage.py `coverage lcov` default; ADR 0007). Missing file ⇒ hard usage error.
- **`coverage.lcov`** — the default on-disk LCOV path for `--reuse-coverage`; what
  coverage.py's `coverage lcov` writes by default (ADR 0007).
- **Covered/Uncovered scan lines** — the two `--scan` output lines
  (`Covered mutation sites: <c>` / `Uncovered mutation sites: <u>`) F3 adds to the §8
  scan block when a coverage source is supplied; F3's observable surface (ADR 0009).

## Run loop & report (F4)

- **Run loop** — the full mutation run (spec §7): strip manifest → discover sites +
  units → build current manifest and diff vs previous (changed function IDs) →
  acquire coverage (F3) and partition → select sites → print header → optional
  uncovered block → baseline → per-site apply/test/classify/restore → restore source →
  print report → re-embed fresh manifest → clean up backup. Composes F1–F3; owns
  selection, baseline, classification, and the §8 run output.
- **Baseline** — one run of `--test-command` (default `pytest`) on the **unmutated**
  source, before any mutant. It **must pass**; on failure the run aborts non-zero with
  `baseline failed: <reason>` and applies no mutants (ADR 0010). Its duration sets the
  mutant timeout.
- **Mutant timeout** — `max(1s, timeout-factor × baseline-duration)`. The `1s` floor
  ports `mutate4go`; a mutant whose test run exceeds it is classified `timeout`
  (ADR 0010, ADR 0011).
- **Classification** — the per-site verdict from the mutated test run: **killed**
  (non-zero exit), **timeout** (exceeded the mutant timeout), **survived** (zero exit).
  `timeout` prints verbatim per-mutant but folds into `Killed` in the report
  (ADR 0011).
- **Selected sites** — the covered sites that actually get mutated, after dropping
  those not in `--lines` (when set) and, when differential, those whose FunctionID is
  unchanged. `selected ⊆ covered ⊆ total`.
- **`effectiveSinceLastRun`** — the differential switch:
  `--since-last-run OR (manifest exists AND not --mutate-all AND not --lines)`.
  Differential is the **default once a manifest exists** — a run with a manifest and
  no overriding flag mutates only changed functions.
- **Differential run** — a run where `effectiveSinceLastRun` is true: only sites in
  changed functions are selected, and the **uncovered block is suppressed** (it prints
  only when not differential and no `--lines`).
- **Run header** — the seven §8 lines: `Mutation run: <file>`, Total / Covered /
  Uncovered / Changed / `Manifest exists` / Selected mutation-site counts, plus the
  warning line over threshold. **No `Mutation workers` line** (serial-only, ADR 0012).
- **Per-mutant progress line** — `[i/total] <status> line <L> <orig> -> <mutant>:
  <functionID>` (colon before functionID; no `worker-<k>` token — ADR 0011, 0012).
- **Mutation Report** — the final block: `Killed: <killed+timeout>` / `Survived:
  <survived>` / `Uncovered: <uncovered>`, followed by a **Survivors** block (one
  `  line <L> <desc> <functionID>` per survivor) **only when survived > 0**.
- **`.mutate4py.bak`** — the crash-safety backup of the stripped (analysis) source,
  written before the per-site loop and removed after. On the **next** run, a
  pre-existing `.bak` (previous run interrupted) is restored first and the tool prints
  `Restored source from backup (previous run was interrupted).`
- **Stale-coverage warning** — `Reusing existing coverage; covered/uncovered
  classification may be stale.`, printed on the `--reuse-coverage` run path before the
  header (run-loop output, not F3's `--scan` surface; ADR 0010).
