# mutate4py — feature decomposition plan

The roadmap for turning [`docs/spec.md`](spec.md) into deliverable, independently
testable features. `spec.md` stays the source-of-truth reference; this file is the
order of work and the boundary of each feature.

**Slicing:** 5 features, one per module, in dependency order (mirrors spec §11
build order and mutate4go's module deps). Each feature is specified one at a time:
frontier brief → user confirmation → `grill-with-docs` → Gherkin → prune →
`ir-dry-checker` → `Background` → end-to-end QA suite → handoff to coder.

**Dependency chain:** F1 → F2 → F3 → F4 → F5. Each feature builds on the prior
and is testable without the later ones.

**Every feature is user-facing** (mirrors the `crap4py` sibling): the CLI exists
from F1, and each feature owns the slice of CLI output it adds — so each gets a
real end-to-end `_qa.feature` that drives the `mutate4py` command, never a project
API. F1 therefore ships a thin CLI (`--scan`) plus the full CI/CD skeleton
(ci.yml + release.yml ported from `crap4py`), landing a runnable, gated, releasable
package. The full flag matrix, mutual-exclusion rules, and run-mode dispatch stay
in F5.

**Sibling templates** (`~/workspace/addi/`): `crap4py` is the Python gold template
(CI, release, `features/*.feature` + `*_qa.feature`, `acceptance/`, `docs/adr`);
`mutate4js` is the module-for-module mirror of this tool; `drywall` is the DRY gate.

---

## F1 — Site discovery & mutation operators (+ CLI & CI skeleton)
**Spec:** §3 (operators), §4 (site discovery & function attribution), §8 (`--scan` output)
**Slug:** `site-discovery`

The analysis core, made observable through a thin CLI, on a green CI pipeline.

**In scope — analysis**
- Walk the whole file's AST; identify every mutation site: arithmetic, relational,
  equality, identity, membership, logical, boolean, and integer `0`/`1` constant.
- The operator catalogue (§3 table) — exactly one mutant per site, one operator/
  literal per site. `*` → `/` only (no `/` → `*`).
- Sort sites by (line, column); assign stable `Index`.
- Attribute each site to its enclosing function by line range; module-level sites
  get empty FunctionID and are still discovered.
- Function-unit definition (§4 [PY]): `func/foo`, `func/Class.m`, async = sync,
  nested `def`/`lambda` fold into enclosing unit, decorators don't create units.
- Byte-offset splice/restore primitive (apply mutant by offset, restore original).

**In scope — user-facing surface (so F1 is end-to-end testable)**
- A thin CLI: `mutate4py <file> --scan` counts sites with no coverage / no test run,
  printing the §8 scan block (`Mutation scan: <file>` / `Total mutation sites: <n>` /
  `Changed mutation sites: <n>` / `Manifest exists: <true|false>` + warning line over
  threshold). For F1, `Changed` = total and `Manifest exists: false` (no manifest yet).
- Minimal arg handling for `<file>` + `--scan` + `--help`; missing file → usage error.

**In scope — project skeleton & CI (mirror `crap4py`)**
- `src/mutate4py/` package + `__main__:main` entry point (pyproject already set).
- `.github/workflows/ci.yml`: ruff lint + format-check, `pytest --cov` → lcov,
  `crap4py` gate, `drywall` DRY gate.
- `.github/workflows/release.yml`: `uv build` + PyPI publish on tag.
- `.gitignore`: extend the existing swarm-infra lines with `crap4py`'s Python
  artifact patterns (`__pycache__/`, `*.pyc`, `*.pyo`, `.venv/`, `.coverage`,
  `coverage.lcov`, `lcov.info`, `*.egg-info/`, `dist/`, `build/`, `.pytest_cache/`,
  `acceptance/parsed/`, `acceptance/generated/`) plus this tool's own backup
  `.mutate4py.bak` (spec §7 crash-safety file).
- `features/site-discovery.feature` + `features/site-discovery_qa.feature`.

**Out of scope (fog → later features)**
- Does NOT acquire or read coverage (F3); `--scan` never touches coverage.
- Does NOT run tests or classify mutants (F4).
- Does NOT read/write the manifest (F2) — so `Manifest exists` is always `false`
  and `Changed` == total in F1.
- Does NOT implement the full flag matrix or mutual-exclusion rules (F5) — only
  `<file>`, `--scan`, `--help`.

---

## F2 — Manifest (embed / extract / diff) (+ thin `--update-manifest` CLI)
**Spec:** §5, plus the thin `--update-manifest` surface (§2 / §8 output string)
**Slug:** `manifest`
**Depends on:** F1 (function units, AST subtrees).

The manifest core, made observable through the one CLI mode that writes it —
mirroring how F1 shipped the analysis core behind a thin `--scan`. Every feature
stays user-facing and gets a real end-to-end `_qa.feature`.

**In scope — manifest core**
- Embed manifest in file footer between `# mutate4py-manifest-begin/-end` markers;
  strip-then-append rules (§5 [PORT] embed).
- Extract: find markers, strip `# ` prefixes, JSON-parse (§5 [PORT] extract).
- Function-unit records (new in F2; F1 exposed `Site.function_id` only): per unit
  `id, name, line, end_line, hash`. Pin `line`/`end_line` semantics against §4's
  unit definition during grilling (decorator/blank-line boundaries).
- Hash = SHA-256 of `ast.dump()` of the unit's subtree ([PY] normalization).
- `module_hash` = SHA-256 of `ast.dump()` of the manifest-stripped module.
- Top-level fields: `version`, `tested_at` (RFC3339), `module_hash`, `functions`.
- Diff current vs previous manifest → `changed` function IDs (changed / new / removed).

**In scope — user-facing surface (so F2 is end-to-end testable)**
- Thin `--update-manifest` mode: strip + re-embed the footer (no mutation run),
  printing the §8 update string. **Idempotent under `ast.dump()` hashing** — when
  the freshly-computed `functions` + `module_hash` equal the already-embedded
  manifest, skip the write and the `tested_at` bump (`Manifest unchanged: <file>`);
  otherwise rewrite and report `Updated manifest: <file>`. This is a deliberate
  divergence from mutate4go's unconditional rewrite, justified by the §5 [PY] hash
  divergence (`ast.dump()` is immune to reformat/comment edits) — record as an ADR
  in grilling. Keeps the file and downstream PRs clean when nothing testable changed.
- `features/manifest.feature` + `features/manifest_qa.feature` (QA drives the real
  `--update-manifest` CLI; never a project API).

**Out of scope (fog → later features)**
- Does NOT decide which sites to mutate based on `changed` (that selection is F4).
- Does NOT acquire coverage (F3).
- Does NOT own the full flag matrix or mutual-exclusion validation (F5) — F2 ships
  `--update-manifest`'s existence and output; F5 wires it into the validation matrix.
- Does NOT touch `--scan`'s manifest interaction (`Changed`/`Manifest exists`) — that
  wiring stays F5; F2's `--update-manifest` is the manifest-writing affordance.

---

## F3 — Coverage gate (LCOV)
**Spec:** §6
**Slug:** `coverage-gate`
**Depends on:** F1 (sites to partition).

**In scope**
- Parse LCOV (reuse crap4py's parser); suffix-based path matching.
- Gate = line coverage: site eligible iff its line has `DA:<line>,<count>` with
  `count > 0`. `BRDA` branch data ignored ([PORT]).
- Partition sites into `covered` / `uncovered`.
- Acquisition modes: `--cov-cmd` (run once, must emit LCOV), `--lcov PATH`,
  `--reuse-coverage` (read from disk; missing file → hard error).

**Open question to resolve in this feature's grilling**
- Default LCOV path for `--reuse-coverage` / `--cov-cmd` output discovery
  (`lcov.info` at repo root — confirm; spec §6 "Open").

**Out of scope**
- Does NOT define the flags' CLI surface/validation (F5) — only their behaviour.
- Does NOT run tests or classify mutants (F4).

---

## F4 — Run loop & report
**Spec:** §7 (run loop), §8 (output format)
**Slug:** `run-loop`
**Depends on:** F1, F2, F3.

**In scope**
- Orchestration (§7 steps 1–9): strip manifest, discover, acquire coverage,
  compute `effectiveSinceLastRun`, `selectSites`, baseline run, per-site
  apply/test/classify/restore, re-embed manifest, cleanup.
- Baseline: run once unmutated, must pass, sets `timeout = max(1s, factor × baseline)`.
- Classification: non-zero → killed; timeout → timeout (counted killed); zero →
  survived.
- Crash safety: `.mutate4py.bak`; restore-on-next-run with the verbatim message.
- All output strings verbatim (§8): header, uncovered block, per-mutant progress,
  final report, survivors block. Worker tokens removed ([PY] §9).

**Out of scope**
- Does NOT parse/validate CLI flags (F5) — assumes parsed options as input.
- Does NOT implement `--scan` / `--update-manifest` output (F5 owns those two
  modes' surface; this feature owns the full-run report).

---

## F5 — CLI surface & validation
**Spec:** §2, plus §8 `--scan` output and `--update-manifest` validation wiring
**Slug:** `cli-surface`
**Depends on:** F1–F4 (wires them behind flags).

**In scope**
- Flag parsing for the whole §2 table (F1 shipped only `<file>`/`--scan`/`--help`,
  F2 added thin `--update-manifest`; F5 adds the rest and the full validation matrix).
- `--scan`'s full interaction with the manifest (`Changed`/`Manifest exists` once
  F2 exists). The `--scan` skeleton itself is delivered in F1; the thin
  `--update-manifest` mode and its §8 output string are delivered in F2. F5 wires
  both into validation/mutual-exclusion — it does not re-create their surface.
- Mutual-exclusion rules ([PORT]): scan/update-manifest exclusive & incompatible
  with execution options; since-last-run/mutate-all/lines pairwise exclusive.
- Numeric-flag validation (reject non-positive / non-integer).
- Missing source file → usage error.
- `--max-workers` removed: passing it is a usage error pointing at serial
  behaviour ([PY] §9).
- `--help` usage text.

**Out of scope**
- Does NOT re-implement run-loop behaviour (F4) — dispatches to it.

---

## Cross-feature notes
- §9 (parallelism removed) is a global constraint, not a feature: it surfaces as
  the `--max-workers` usage error (F5) and the absence of worker tokens in output
  (F4). No standalone spec.
- §1 (substrate/distribution) and §11 (build order) are project setup, already
  reflected in `pyproject.toml`; not features.
- Reuse from siblings (`crap4py` LCOV parser, `gabadi/mutate4js` output strings)
  is an implementation concern flagged per feature, not a feature itself.
