# Python discovers unary `not` and unary `-` sites

A unary `not` or `-` Site deletes the operator token and the spaces after it. The replacement is one space only when both neighbours are word characters.

## Considered Options

- **A `-` Site only on a numeric operand (the mutate4java rule).** Python has no static types, so removing `-` from any operand is a real change.
- **No `-` Site on a negative literal.** `-1` keeps two Sites, `-` and `1`.
- **Always one space.** It breaks a statement-level `not` in a multi-line block: the indent of the mutated line no longer agrees with its siblings.
- **Always empty.** `if-x:` becomes `ifx:` (a SyntaxError), and `return-x` becomes `returnx` (a different meaning).
- **Treat `not in` and `is not` as unary.** They are `Compare` operators, and they are mutated already.
