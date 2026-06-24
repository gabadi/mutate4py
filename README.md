# mutate4py

Mutation testing for Python. Discovers mutation sites, applies each one, runs your
tests, and reports killed, survived, and uncovered mutations — with an
**embedded-in-source manifest** so differential reruns survive a clone with zero CI
setup.

A faithful Python port of [unclebob/mutate4go](https://github.com/unclebob/mutate4go),
with the user-facing contract cross-checked against
[unclebob/clj-mutate](https://github.com/unclebob/clj-mutate). Where Python forces a
divergence (coverage acquisition, the manifest hash, no parallel workers) it is
marked `[PY]` and justified in [`docs/spec.md`](docs/spec.md).

> Status: **scaffold**. Not yet functional.

## Install

```bash
uvx mutate4py        # run without installing
uv tool install mutate4py
```

## Usage

```bash
mutate4py path/to/file.py --test-command "pytest" --lcov lcov.info
```

Generate `lcov.info` with [coverage.py](https://coverage.readthedocs.io/):

```bash
pytest --cov --cov-branch --cov-report=lcov:lcov.info
```

See `mutate4py --help` and the [spec](docs/spec.md) for the full flag set.

## How it differs from mutate4go (`[PY]`)

- **Serial only** — `--max-workers` is removed; the copy-isolated-worker model is
  unsound under Python editable installs (`pip install -e .`). Mutation is in-place,
  which is correct everywhere.
- **Coverage is acquired explicitly** — `--lcov` / `--cov-cmd` / `--reuse-coverage`
  (Python has no universal `-coverprofile` equivalent).
- **Manifest hash is structural** (`ast.dump()`), so reformatting and comment edits
  don't trigger a re-test, but any behavior-affecting edit does.
- **Operators are localized** to Python: adds `and`/`or`, `True`/`False`, and the
  identity/membership negation flips `is`/`is not` and `in`/`not in`.

## Develop

Python ≥ 3.10, stdlib `ast` (zero runtime deps), packaged with `hatchling`.

```bash
uv sync
uv run mutate4py --help
uv run pytest
```
