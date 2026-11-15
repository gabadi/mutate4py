# Nested defs fold into the enclosing unit; the operator set is localized, not extended

**Status:** accepted

A site is attributed to its enclosing **named** function unit by line range. Nested
`def` and `lambda` are **not** separate units — their sites fold into the enclosing
named unit. Decorators do not create a unit; the decorated `def` is the unit. Sites
outside any function and any class keep an empty FunctionID and are still mutated.

**Amendment (0.3.3): a class is a unit for its own body.** A Site in a class body,
outside every method, takes the id `class/<Name>` of its innermost class. The Manifest
holds an entry for each class outside a function, so a Survivor there is recorded
(ADR 0026). The entry's hash covers the class header, its decorators and its
statements that are not a `def` or a nested class, so an edit to a method leaves the
class entry alone. A class inside a function folds into that function, as a nested
`def` does.

## Divergence from crap4py ADR 0003 — deliberate

crap4py decides the **opposite**: every nested/inner `def` is its own scored unit.
Both are right for their tool. crap4py scores each function independently, so a
nested def must be its own row. mutate4py attributes sites to a *manifest unit*
whose hash drives differential reruns; splitting nested defs would fragment the
manifest and diverge from mutate4go's flat `functionIDAtLine`.

This note exists so a reader who knows crap4py does not assume its rule here.

**Rejected:**
- *Split nested defs into units (the crap4py rule)* — fragments the manifest.
- *Add `/`→`*`, augmented-assignment (`+=`/`-=`), unary removal* — these are new
  mutation **categories** no port introduced. The rule is localize-per-language, not
  fabricate. Revisit only on field demand.
  Unary `not` and unary `-` removal is superseded for Python: see ADR 0024.
