# `--update-manifest` is idempotent — no rewrite when nothing structural changed

**Status:** accepted

mutate4go rewrites the manifest footer unconditionally, bumping `tested_at` every
time. mutate4py skips the write entirely when the freshly-computed `functions` and
`module_hash` equal the embedded manifest, printing `Manifest unchanged: <file>`
instead of `Updated manifest: <file>`. The file stays byte-identical, so repeated
runs don't churn diffs.

**Do not "fix" this back to the port.** It is a deliberate divergence, and it exists
only because the hash is structural (ADR 0005): under mutate4go's
any-textual-edit-re-tests contract there would be nothing to be idempotent about.
