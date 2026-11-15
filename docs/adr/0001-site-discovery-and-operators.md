# Nested defs fold into the enclosing unit; the operator set is localized, not extended

A nested `def` or `lambda` folds into its enclosing named Function unit, and the Site operators are the ones the upstream ports use.

## Considered Options

- **A unit for each nested `def` (the crap4py rule, its ADR 0003).** It fragments the Manifest, and mutate4go attributes a line to one flat unit (`functionIDAtLine`).
- **New mutation categories: `/` to `*`, `+=` and `-=`.** No port has them. Each language localizes the upstream operators; it does not make new ones.
