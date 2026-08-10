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

## Multiple targets & glob patterns

The positional argument is zero or more targets — literal paths or glob
patterns, expanded with `glob.glob(..., recursive=True)`:

```bash
mutate4py 'src/**/*.py' --check-manifest
```

How many paths that resolves to decides the run shape (ADR 0017): **one**
path runs exactly like today (single-file or directory dispatch); **two or
more** run as a single **union batch** — one baseline, one exit code, `.py`
files under every root deduped by realpath:

```bash
mutate4py src/mutate4py/__main__.py src/mutate4py/_workspace.py --check-manifest
```

## uv workspace autodiscovery

Run `mutate4py` with **no** positional argument inside a
[uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/) and it
finds its own targets: it climbs from the current directory to the nearest
`pyproject.toml` declaring `[tool.uv.workspace]`, then processes that root
(recursively) plus every directory matched by `members` that has its own
`pyproject.toml`:

```toml
# pyproject.toml at the workspace root
[tool.uv.workspace]
members = ["packages/*"]
exclude = ["packages/legacy"]
```

```bash
cd my-workspace && mutate4py --check-manifest   # no target — discovers packages/*
```

`exclude` is honored on top of what `members` requires, pruning both the
member list and the workspace root's recursive walk. A directory matched by
`members` but missing its own `pyproject.toml` is skipped rather than
erroring — a deliberate divergence from `uv` itself, since mutate4py's job is
finding Python files, not validating the workspace. No workspace found (or no
`pyproject.toml` at all) is a usage error, exit 2, naming the path it
inspected. Full rationale in [ADR 0017](docs/adr/0017-multi-root-targets-and-uv-workspace-autodiscovery.md).

## Directory mode

Point `mutate4py` at a directory instead of a file and every `.py` file under it is
processed in turn. The walk prunes `__pycache__`, `venv`, `node_modules`, and any
dot-directory (`.git`, `.venv`, …); `build/` and `dist/` are left walkable (issue
#22 — previously only `__pycache__` was pruned). This works for `--scan`,
`--update-manifest`, `--check-manifest`, and scored runs alike.

```bash
mutate4py src/ --check-manifest
```

`--exclude PATTERN` drops files from that walk. It is repeatable, and a file is
skipped if it matches **any** pattern — never scanned, never reported, never able to
fail the run:

```bash
mutate4py src/ --check-manifest \
  --exclude '**/__init__.py' \
  --exclude '**/migrations/**' \
  --exclude '**/vendor/**'
```

Patterns are matched case-sensitively on every platform, against the whole path
as walked — i.e. built from the path you passed, so `src/` yields
`src/pkg/mod.py`. `--exclude` shares its glob dialect with positional targets and
uv workspace `members`/`exclude` (ADR 0017): `*` matches exactly one path segment
and never crosses `/`; `**` matches zero or more segments, but only when it
stands alone as a whole `/`-bounded component (glued to literal text, e.g.
`foo**bar`, it degrades to an ordinary same-segment wildcard). Two consequences
worth knowing:

- `*` stays within one path segment, and the path always has the walked
  directory prefixed on it (see the next point) — so `--exclude '*.py'` matches
  **nothing**: it can never match a string containing `/`. Even a file directly
  inside the target (`src/a.py`) needs `'src/*.py'` or `'**/*.py'`, and
  `'**/vendor/**'` (not `'*/vendor/*'`) to match `vendor/` wherever it sits.
- A bare basename never matches: the path always has the target directory
  prefixed on it (even for a file sitting directly inside the target), so
  `'__init__.py'` matches nothing at any depth. Always prefix it, e.g.
  `'**/__init__.py'`.

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
- **Manifest hash is structural** (`ast.unparse()`), so reformatting and comment edits
  don't trigger a re-test, but any behavior-affecting edit does.
- **Operators are localized** to Python: adds `and`/`or`, `True`/`False`, and the
  identity/membership negation flips `is`/`is not` and `in`/`not in`.

## Develop

Python ≥ 3.11, stdlib `ast` (zero runtime deps), packaged with `hatchling`.

```bash
uv sync
uv run mutate4py --help
uv run pytest
```
