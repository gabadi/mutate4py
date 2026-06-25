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
  `func/Class.m` for a method. Nested `def`/`lambda` **fold into** the enclosing
  named unit (NOT separate units — deliberately the opposite of crap4py's
  per-function scoring; ADR 0001). Module-level sites have an **empty FunctionID**
  and are still mutated.
- **FunctionID** — the unit id attributed to a site by line range; empty for
  module-level sites.
- **Index** — a site's stable position after sorting all sites by `(line, column)`.
- **Splice / restore** — applying a mutant by byte-offset source edit and rewriting
  the original back. The in-place model (one file on disk → one mutant at a time);
  serial only, editable-install-proof (spec §9).
- **`--scan`** — read-only CLI mode printing site *counts* only (no coverage, no
  tests, no write, no per-site listing; ADR 0001, 0002).
- **Manifest** — the JSON block embedded in the file footer between
  `# mutate4py-manifest-begin/-end`, recording per-unit hashes for differential
  reruns (spec §5). Owned by F2; **absent in F1** (ADR 0002).
- **Differential rerun** — re-testing only sites whose function unit changed since
  the last manifest; the default once a manifest exists (spec §7).
- **Covered / uncovered** — partition of sites by LCOV line coverage; a site is
  covered iff its line has `DA:<line>,<count>` with `count > 0` (spec §6, F3).

## Faithful-port tags

- **[PORT]** — reproduce mutate4go's behavior exactly.
- **[PY]** — a deviation forced by Python / its ecosystem, justified in the spec.

## Sibling repos (`~/workspace/addi/`)

- `crap4py` — Python gold template (CI, release, features + `*_qa.feature`,
  `docs/adr`). Pattern source for skeleton/CI/`.gitignore`.
- `mutate4js` — the module-for-module mirror of this tool. Its `docs/adr/`
  pre-resolve several F1 questions; cited where relevant.
- `drywall` — the DRY gate binary (CI downloads its release).
