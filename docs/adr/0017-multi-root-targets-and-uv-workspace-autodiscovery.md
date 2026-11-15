# Glob dialect is hand-rolled; workspace autodiscovery uses stdlib `tomllib` only

Positional targets, `--exclude` and uv `members` and `exclude` share one glob dialect: `*` stays in one path segment, and `**` as a full component matches zero or more segments.

## Considered Options

- **`pathlib.PurePath.full_match`.** It has this dialect, but only on Python 3.13 and later. Delete `_glob_dialect.py` when the floor is 3.13.
- **A `tomli` dependency.** The floor went to Python 3.11 for stdlib `tomllib` instead.
- **Split `--exclude` on commas.** A glob can contain a comma (`'*/{a,b}/*'`), so `--exclude` is `action="append"`.
- **Run `uv` to find the members.** Autodiscovery reads `pyproject.toml` and starts no process.
- **Fail on a matched member that has no `pyproject.toml`, as `uv` does.** mutate4py finds Python files and does not validate a workspace, so it skips that directory.
