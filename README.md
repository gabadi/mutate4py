# mutate4py

Mutation testing for Python. Discovers mutation sites, applies each one, runs your
tests, and reports killed, survived, and uncovered mutations — with an
**embedded-in-source manifest** so differential reruns survive a clone with zero CI
setup.

A faithful Python port of [unclebob/mutate4go](https://github.com/unclebob/mutate4go),
with the user-facing contract cross-checked against
[unclebob/clj-mutate](https://github.com/unclebob/clj-mutate). Where Python forces a
divergence (coverage acquisition, the manifest hash) it is marked `[PY]` and
justified in [`docs/spec.md`](docs/spec.md).

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

## Directory mode

Point `mutate4py` at a directory instead of a file and every `.py` file under it is
processed in turn (`__pycache__` is skipped). This works for `--scan`,
`--update-manifest`, `--check-manifest`, and scored runs alike.

```bash
mutate4py src/ --check-manifest
```

`--exclude PATTERN` drops files from that walk. It is repeatable, and a file is
skipped if it matches **any** pattern — never scanned, never reported, never able to
fail the run:

```bash
mutate4py src/ --check-manifest \
  --exclude '*/__init__.py' \
  --exclude '*/migrations/*' \
  --exclude '*/vendor/*'
```

Patterns are matched with `fnmatch.fnmatchcase` (case-sensitive on every platform)
against the whole path as walked — i.e. built from the path you passed, so `src/`
yields `src/pkg/mod.py`. Two consequences worth knowing:

- `*` crosses `/`, so `--exclude '*.py'` excludes **everything**, and `'*/vendor/*'`
  already matches at any depth. There is no special `**` handling.
- A bare basename only matches at the root: use `'*/__init__.py'`, not
  `'__init__.py'`.

Excluded files are silent by default; `--verbose` prints one `Excluded: <path>` line
each. If the exclusions leave nothing to process — or the directory holds no `.py`
files at all — the command prints `error: no Python files to process.` and exits
**2**, rather than passing vacuously. `--exclude` also applies to a single-file
target: a target that matches is not analysed, and exits 2 the same way.

## How it differs from mutate4go (`[PY]`)

- **`--max-workers` uses clone-per-worker, not tree-copy+`cwd`** — mutate4go's
  tree-copy model is unsound under Python editable installs (`pip install -e .`), so
  each worker gets its own `uv`-provisioned venv instead.
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
