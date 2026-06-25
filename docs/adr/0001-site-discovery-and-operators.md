# ADR 0001 — Mutation site discovery & the operator catalogue

- Status: accepted
- Date: 2026-06-25
- Feature: F1 (`site-discovery`)
- Spec: docs/spec.md §3, §4

## Context

mutate4py ports `unclebob/mutate4go`, cross-checked against `unclebob/clj-mutate`,
and mirrors `gabadi/mutate4js` module-for-module. F1 owns the analysis core: given
one Python file, find every place a mutation could be applied (a *site*), decide
which native operator/literal each site mutates to, and attribute each site to a
*function unit* so later differential reruns can scope by unit.

mutate4go discovers sites by walking the Go AST; mutate4py walks the Python `ast`.
The operator set is localized per language — Uncle Bob's documented practice,
proven by clj-mutate adding `inc`/`dec`, `=`/`not=`, `if-not`. The grilling (spec
§0, §3) locked the Python set.

## Decision

**Sites.** Walk the whole file's `ast`. Every node below is one site, mutated to
exactly one mutant (one operator/literal per site):

| Category | Mutation |
| --- | --- |
| Arithmetic | `+`→`-`, `-`→`+`, `*`→`/` |
| Comparison (relational) | `>`→`>=`, `>=`→`>`, `<`→`<=`, `<=`→`<` |
| Equality (negation flip) | `==`→`!=`, `!=`→`==` |
| Identity (negation flip) | `is`→`is not`, `is not`→`is` |
| Membership (negation flip) | `in`→`not in`, `not in`→`in` |
| Logical | `and`→`or`, `or`→`and` |
| Boolean | `True`→`False`, `False`→`True` |
| Constant | integer `0`→`1`, `1`→`0` |

- **`*`→`/` only**; never `/`→`*` (mutate4go [PORT]).
- Identity/membership flips are the Python localization of the equality category
  (`if x is None:` / `if x in valid:` are the dominant idiomatic comparisons) —
  negation flips, never cross-coercion-family swaps.
- **Excluded, no site emitted:** augmented assignment (`+=`/`-=`), unary removal,
  and any cross-family swap. These are *new categories* no port introduced
  (unary/null were fabrications corrected in mutate4js spec §10). Revisit only on
  field demand.

**Ordering & index.** Sort sites by `(line, column)`; assign a stable `Index`.
Two runs over identical source produce identical site lists.

**Function attribution & units** (spec §4 [PY]):

- A site is attributed to its enclosing function *by line range*.
- Top-level `def foo` → unit id `func/foo`. `async def foo` → `func/foo` (same as
  sync).
- A method `def m` inside `class C` → `func/C.m` (qualified by enclosing *classes*).
- A site outside any function gets an **empty FunctionID** and is **still
  discovered** (module-level code is not skipped).
- **Nested `def` and `lambda` are NOT separate units.** Their sites attribute to
  the enclosing *named* unit by line range. This mirrors mutate4go's
  `functionIDAtLine` and clj's "top-level forms". (See the divergence note below —
  this is the opposite of crap4py ADR 0003.)
- Decorators do not create a unit; the decorated `def` is the unit. A unit's line
  range is the `def`'s own `ast` span (`node.lineno`..`node.end_lineno`), starting
  at the `def` line, not the decorator line.

**Apply/restore primitive.** Mutation is a byte-offset source splice: compute
absolute byte offsets from `(lineno, col_offset)` / `(end_lineno, end_col_offset)`
over the file's line index (Python `ast` col offsets are UTF-8 byte offsets within
a line); apply = splice mutant text, restore = rewrite original. F1 builds this
primitive; F4 drives it under the run loop.

## Divergence from crap4py ADR 0003 (deliberate, flagged)

crap4py ADR 0003 decides **every nested/inner `def` is its own scored unit**
(enclosing functions do not qualify; only classes do). mutate4py decides the
**opposite**: nested `def`/`lambda` fold into the enclosing named unit.

Both are correct for their tool. crap4py *scores each function independently*
(per-function CRAP), so a nested def must be its own row. mutate4py *attributes
sites to a manifest unit* whose hash drives differential reruns, faithfully
mirroring mutate4go's flat `functionIDAtLine`. Splitting nested defs into separate
units would diverge from mutate4go and fragment the manifest. The two tools share a
codebase family but not this rule; this note exists so a reader who knows crap4py
does not assume its rule here.

## Consequences

- Per-operator and per-attribution correctness is verified by the discovery
  module's **unit tests**, not through the CLI — reaching every operator through
  `--scan`/run output is brittle (mutate4js ADR 0001). The CLI surfaces only the
  *count* (ADR 0002 here).
- Module-level sites with empty FunctionID still mutate, so a constant or operator
  in top-level code is not silently skipped.
- The fold-nested-defs rule keeps the manifest unit set flat and stable, which F2's
  hashing and F4's differential selection depend on.

## Alternatives considered

- **Split nested defs into units (crap4py rule)** — rejected: diverges from
  mutate4go's `functionIDAtLine` and fragments the manifest.
- **Add `/`→`*`, augmented-assignment, unary removal** — rejected: new categories
  no port introduced; the spec's localize-don't-fabricate principle (§3) forbids it
  absent field demand.
