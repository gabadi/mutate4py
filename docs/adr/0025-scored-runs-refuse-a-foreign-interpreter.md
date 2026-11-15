# A scored run refuses a foreign interpreter instead of switching to the project's

A scored run exits 2 before the Baseline when the `.venv` of the project exists and is not the running interpreter.

## Considered Options

- **Switch to the Python of the project.** The forking executor runs tests in a fork of this process and cannot change interpreter. It would fall back to subprocesses or be turned off.
- **A warning only.** Agents act on exit codes, not on stderr. A warning lets wrong results exit 0, and their false Survivors look like real test gaps.
- **`VIRTUAL_ENV`.** A stale activation misleads it, and it is not set when the venv python runs directly.
- **`sys.prefix != sys.base_prefix`.** `uvx` and `uv tool` environments are venvs too, so they pass. It proves "a venv", not "the project environment".
- **`realpath(sys.executable)`.** A venv python is a symlink to the base Python, so different venvs become one.
