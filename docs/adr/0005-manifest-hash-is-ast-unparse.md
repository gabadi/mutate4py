# Manifest hash is SHA-256 of `ast.unparse()`, not whitespace-collapsed text

The Unit hash is `sha256(ast.unparse(node))` over the AST subtree of the unit.

## Considered Options

- **mutate4go's `normalize`: collapse each whitespace run to one space.** It does not see indentation. In Python, indentation is block structure, so a re-indent that moves a statement into or out of a block gives the same hash, and the function is not tested again.
