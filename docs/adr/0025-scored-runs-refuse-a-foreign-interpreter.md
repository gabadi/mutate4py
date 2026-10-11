# A scored run refuses a foreign interpreter instead of switching to the project's

**Status:** accepted

A scored run (Baseline or Mutant run) exits 2 before any Baseline when the project's
`.venv` exists and is not the running interpreter. A target's project root is its
nearest ancestor with `pyproject.toml` (itself included), else the cwd; the cwd is
always checked too, since workspace autodiscovery resolves to it. Both sides go
through `realpath`. No `.venv/bin/python` means no check. A `uv run --with` overlay counts as the project environment because the project's site-packages is on `sys.path` through site processing (not `PYTHONPATH`), even though its prefix is temporary.

Exempt, since they never run tests: `--scan`, `--update-manifest`, `--check-manifest`.

## Rejected alternatives

- **Switch to the project's Python.** The forking executor runs tests in a fork of
  this process and cannot change interpreter. It would fall back to subprocesses or
  be disabled, which undoes ADR 0020.
- **Warning only.** Agents act on exit codes, not stderr (ADR 0018). A warning lets
  wrong results exit 0, and their false survivors look like real test gaps.
- **`VIRTUAL_ENV`.** A stale activation misleads it, and it is unset when the venv
  python runs directly.
- **`sys.prefix != sys.base_prefix`.** `uvx` and `uv tool` envs are venvs too, so
  they pass. It proves "some venv", not "the project env".
- **`realpath(sys.executable)`.** A venv python symlinks to the base Python, so
  distinct venvs collapse into one.
