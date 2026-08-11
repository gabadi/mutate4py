# Manifest hash is SHA-256 of `ast.unparse()`, not whitespace-collapsed text

**Status:** accepted

mutate4go hashes a function unit as `sha256(normalize(text))` where `normalize`
collapses whitespace runs to single spaces — contract: *any textual edit re-tests*.
Collapsing whitespace is wrong for Python, where indentation defines block
structure: a re-indent that moves a statement in or out of a block would hash
identically to the original, silently dropping a re-test on a real behaviour change.

mutate4py instead hashes the **canonical unparse of the unit's AST subtree**:
`sha256(ast.unparse(node))`, and `module_hash = sha256(ast.unparse(tree))` over the
manifest-stripped source. Reformatting, comment edits, and moving a function leave
the hash alone; rename, literal, operator, and re-block edits change it.

**Known limitation, unfixed:** `ast.unparse` is not a frozen contract across CPython
minors (PEP 701 changed f-string unparsing). Two machines on different minors can
compute different hashes for byte-identical source — one passes `--check-manifest`,
the other fails. Pin the interpreter minor in CI. Hash tests compare hashes
*relatively* (same hash before and after a reformat), which holds on any single
interpreter and so cannot detect this.

**Rejected:** mutate4go's whitespace-collapse `normalize` — indentation-blind, and
Python indentation is semantic.
