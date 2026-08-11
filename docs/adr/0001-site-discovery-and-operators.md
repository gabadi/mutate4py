# Nested defs fold into the enclosing unit; the operator set is localized, not extended

**Status:** accepted

A site is attributed to its enclosing **named** function unit by line range. Nested
`def` and `lambda` are **not** separate units — their sites fold into the enclosing
named unit. Decorators do not create a unit; the decorated `def` is the unit. Sites
outside any function keep an empty FunctionID and are still mutated.

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
