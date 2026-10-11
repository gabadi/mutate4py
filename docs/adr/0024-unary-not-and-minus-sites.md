# Python discovers unary `not` and unary `-` sites

**Status:** accepted. **Supersedes:** the "unary removal" item in ADR 0001's rejected list.

Python sites now include `UnaryOp(Not)` (token `not`) and `UnaryOp(USub)` (token `-`), each mutated to deletion. The site span is the operator token plus the following `[ \t]*` run, never the operand, because operand spans exclude parentheses (`-(a + b)`). The replacement is one space only when both neighbours match `\w`, otherwise empty: `if-x:` becomes `if x:`, `return-x` becomes `return x`, and `if not ok:` becomes `if ok:`.

Upstream unclebob/mutator inherits Java's "delete `!` and unary `-`" for Python (README L96, L100), and mutate4java already has both. ADR 0001's "no port introduced" premise no longer holds for Python.

Rulings:
- **Manifest pick-up.** Existing manifest hashes stay valid, but `_filter_by_fn` scans only changed functions. Unary sites in unchanged, already-manifested functions are picked up when that function changes or with `--mutate-all`.
- **Zero literals.** Unary `-` whose operand is an `ast.Constant` of exact type `int`, `float`, or `complex` with value `== 0` yields no site: `-0`, `-0.0`, `-0j`, `-(0)`. `bool` is excluded by exact type, so `-False` keeps its site, and `-0` still yields its `0` to `1` Constant site. The rule is exact on type and value, not on sign: `-0.0` differs from `0.0` under `math.copysign`, and that sign-only difference is the cost of excluding it.
- **Description.** `Site.desc` shows the whole node, as binop and compare sites do: `not x -> x`, `-y -> y`, `not(a) -> (a)`. The splice span stays the operator token.

**Rejected:**
- *Numeric-only gate on `-`* (mutate4java's approach): Python has no static types, so removing `-` from any operand is a real change.
- *Skip negative literals*: `-1` yields two sites (`-` and `1`). Kept.
- *Always one space*: breaks a statement-level `not` in a multi-line block, where the mutated line's indent no longer matches its siblings.
- *Always empty*: `if-x:` becomes `ifx:` (SyntaxError); `return-x` becomes `returnx` (changes meaning).
- *Treat `not in` and `is not` as unary*: they are `Compare` operators and already mutated.
