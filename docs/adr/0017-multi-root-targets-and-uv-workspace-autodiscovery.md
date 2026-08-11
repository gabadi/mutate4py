# Glob dialect is hand-rolled; workspace autodiscovery uses stdlib `tomllib` only

**Status:** accepted

One glob dialect is shared by positional targets, `--exclude`, and uv
`members`/`exclude`: `*` matches exactly one path segment and never crosses `/`;
`**` matches zero or more segments, but only when it stands alone as a whole
`/`-bounded component (`foo**bar` degrades to a same-segment wildcard).

**Rejected, and why each rejection matters:**

- **`fnmatch.fnmatchcase`** (the pre-existing dialect) — its `*` crossed `/`
  unconditionally and it had no real `**`, so `--exclude '*.py'` silently matched
  every file at every depth.
- **`pathlib.PurePath.full_match`**, which has this dialect natively — 3.13+ only.
  Hence the hand-rolled `_glob_dialect.py`. Delete it once the floor reaches 3.13.
- **A `tomli` dependency** — the tool ships with zero runtime dependencies. Raising
  the Python floor to 3.11 for stdlib `tomllib` was preferred to giving that up.
- **Comma-splitting `--exclude`** (the `--lines` precedent) — a glob may legitimately
  contain a comma (`'*/{a,b}/*'`), so splitting would corrupt valid patterns.
  `action="append"` instead.
- **Shelling out to `uv`** — autodiscovery reads `pyproject.toml` directly, never
  spawns `uv`.

**Deliberate divergence from `uv` itself:** a directory matched by
`[tool.uv.workspace].members` that has no `pyproject.toml` is **skipped silently**;
real `uv` errors. mutate4py's job is finding Python files, not validating a
workspace.
