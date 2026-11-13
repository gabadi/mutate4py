# mutate4py

Mutation testing for Python. Discovers mutation sites, applies each one, runs your
tests, and reports killed, survived, and uncovered mutations — with an
**embedded-in-source manifest** so differential reruns survive a clone with zero CI
setup.

Originally a Python port of [unclebob/mutate4go](https://github.com/unclebob/mutate4go),
with the user-facing contract cross-checked against
[unclebob/clj-mutate](https://github.com/unclebob/clj-mutate). Where Python forced a
divergence — coverage acquisition, the manifest hash, parallel worker isolation —
the reasoning is recorded in [`docs/adr/`](docs/adr/). Release notes are in
[CHANGELOG.md](CHANGELOG.md).

## Install

```bash
uvx mutate4py        # run without installing
uv tool install mutate4py
```

mutate4py depends on [coverage.py](https://coverage.readthedocs.io/) (`coverage>=7.10`),
which the run uses to measure coverage itself.

## Usage

```bash
mutate4py path/to/file.py
```

pytest is the only supported test runner, invoked directly (never through a
shell). Pass extra pytest arguments with `--pytest-args "ARGS"`, e.g.
`--pytest-args "-x -k calc"`.

Nothing has to be generated first. Each scored run takes its own **Measurement**
before any Mutant runs: one pytest session under coverage.py, which gives the unmutated
pass requirement, the coverage gate and the test map (ADR 0027). If your suite has slow
tests that mutation should not run, select the rest with `--pytest-args`; this
repository's own selection is `-m 'not integration and not component'` (ADR 0023).

See `mutate4py --help` for the full flag set, and the flags table below for the ones
that shape a scored run.

## Flags

| Flag | Default | What it does |
|------|---------|--------------|
| `--scan` | | Count mutation sites; no test run. |
| `--update-manifest` | | Embed or refresh the manifest in each file; no test run. |
| `--check-manifest` | | Verify the manifests: unit hashes, recorded Survivors and equivalent markers. No test run, so it does not check tests digests. |
| `--manifest-file` | off | Store the manifest as sidecar JSON (`<file>.manifest.json`) instead of embedding it. |
| `--exclude PATTERN` | | Skip files whose path matches `PATTERN`. Repeatable. See [Directory mode](#directory-mode). |
| `--mutate-all` | off | Re-score every covered function, not only the changed ones. |
| `--allow-survivors` | off | Exit 0 instead of 3 when a scored run leaves unaccepted Survivors. |
| `--max-workers N` | serial | Run Mutants in `N` parallel Workers. See [Worker provisioning cost](#worker-provisioning-cost-and-when-parallelism-pays-off). |
| `--no-fork` | off | Force the subprocess executor instead of the forking executor. See [Executors](#executors). |
| `--pytest-args ARGS` | | Extra pytest arguments, as one shell-quoted string. |
| `--timeout-factor N` | 10 | Factor on the budget of a Mutant's own tests in its timeout. See [Timeouts](#timeouts). |
| `--min-timeout S` | 5.0 s | Floor, in seconds, on a Mutant's timeout before the per-Mutant overhead is added. See [Timeouts](#timeouts). |
| `--mutation-warning N` | 50 | Warn when the run's mutation sites exceed `N`. |
| `--verbose` | off | Print more detail, e.g. one `Excluded:` line per file `--exclude` skipped. |

The flags removed in 0.3.0 are listed under [Removed in 0.3.0](#removed-in-030).

## Multiple targets & glob patterns

The positional argument is zero or more targets — literal paths or glob
patterns, expanded with `glob.glob(..., recursive=True)`:

```bash
mutate4py 'src/**/*.py' --check-manifest
```

How many paths that resolves to decides the run shape (ADR 0017): **one**
path runs exactly like today (single-file or directory dispatch); **two or
more** run as a single **union batch** — one Measurement, one exit code, `.py`
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

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Ok. |
| 1 | Measurement or worker failure (coverage, or the unmutated suite not passing); `--check-manifest` finds the Manifest missing, stale, or recording an unaccepted Survivor. |
| 2 | Usage, parse or selection error, including a flag removed in 0.3.0. |
| 3 | A scored run left an unaccepted Survivor, a recorded one included (`--allow-survivors` exits 0 instead). |

A batch (a directory or several targets) exits with its most severe per-file code: 2 > 1 > 3 > 0.

A Survivor you have judged equivalent can be accepted with a comment on the line the report prints for it (for an expression spanning several lines, its first line):
`x = a > b  # mutate4py: equivalent same result for every input`. The accepted Survivor
does not fail the run. The report lists it under `Accepted equivalents:` with its
reason, and the Manifest records it under `accepted` (ADR 0026). The marker accepts
every survived Mutant on its line, so to accept only one of two, split the line. An
empty reason exits 2 before the Measurement runs.

## Test selection and the Measurement

Each scored run takes its Measurement (ADR 0027) before any Mutant runs. It is one
pytest session of the run's unit tests under coverage.py's `ctrace` core, with each test
in its own context. That one session gives:

- the **Baseline**: the unmutated suite must pass, or no Mutant runs;
- the **coverage gate**: a Site counts as covered when any test reached its line;
- the **Test map**: the named tests that reached each covered line.

From the Test map most Mutants get **narrowed** to just the tests that reached their
line. A `static` outcome — the line ran only under coverage's whole-run context, e.g.
module-level constants, imports, or class headers — is not a narrowing failure: that
Mutant runs the full test set verbatim. A run with several `static` Mutants will show a
longer tail than a fully narrowed one; that's expected, not a defect. The report prints
`Test selection: narrowed <n>, static <k>`. See
[ADR 0018](docs/adr/0018-test-selection-three-case-no-silent-fallback.md) for the two
outcomes.

**Survivor confirmation.** A narrowed run can miss a killing test that matters only
through state it reads. So before a Survivor is reported, it is re-run with the full test
set, in a fresh interpreter through the subprocess executor. It counts only if it survives
that run too; a kill, or a timeout, folds into killed (ADR 0011). Accepted equivalents are
not confirmed. The `Time:` line shows the cost as
`confirmation <s> (<n> run, <k> killed)`. See ADR 0018 (amendment #97) and
[ADR 0028](docs/adr/0028-fork-server-harness-mode-and-swap-mode.md).

## Tests digest and the rerun skip rule

A scored run re-scores only the **changed** functions. A function is changed when any of
these hold: its Unit hash differs (formatting and comment edits do not count, and
behaviour-affecting edits do); its **Tests digest** differs; it is Unscored; an accepted
equivalent lost its marker; or it records Survivors and has no digest yet, so a 0.2.x
entry with Survivors is retried once.

The Tests digest is a SHA-256 over the test inputs that can reach the function's covered
Site lines: the test files the Measurement shows reaching them, their conftests, the
run's support files, the pytest table of `pyproject.toml`, the pytest ini file and
`uv.lock`. So an edit to a test that reaches a function re-scores that function even
though the function itself did not change.

A function whose Unit hash and digest are both unchanged is **skipped**, even when it
records Survivors. Its recorded Survivors print under `Recorded survivors (not re-run):`,
apart from the run's own Survivors, and they count toward the exit code: exit 3, or 0 with
`--allow-survivors`. A rerun with nothing changed skips the Measurement and the Mutants,
and reports the recorded Survivors on the same terms. `--mutate-all` re-scores every
covered function regardless.

`--check-manifest` checks hashes, recorded Survivors and equivalent markers, not digests:
it runs no test, so it cannot recompute one, and a stale digest does not fail it. See
[ADR 0029](docs/adr/0029-per-function-tests-digest-and-skip-rule.md) and
[ADR 0026](docs/adr/0026-survivors-fail-the-run-and-stay-in-the-manifest.md).

## Timeouts

A Mutant's timeout is:

```
max(--min-timeout, --timeout-factor × budget) + per-Mutant overhead
```

The **budget** is the summed measured durations of the tests that Mutant runs, plus the
largest fixture setup seen in their files. The **per-Mutant overhead** is the
Measurement's wall time minus the summed durations of its tests: the time pytest spends
outside the tests, such as its bootstrap and its plugins. It comes from the Measurement
itself, with no extra pytest pass. A timed-out Mutant counts as killed (ADR 0011).

The defaults are `--timeout-factor 10` and `--min-timeout 5.0` s. The `--min-timeout`
default was 1.0 s before 0.3.0.

## Per-Mutant plugin cost

Every Mutant runs pytest as a fresh session, whether the interpreter is warm or
cold — no execution model removes plugin cost at collection or session scope. A
warm interpreter (the forking executor) skips re-importing plugins, but their
session-scope hooks still fire on every invocation; measured against one advisory
plugin in this project, that cost was ~1.6s cold and still ~0.8s warm.

Two plugins mutate4py neutralises automatically for Mutant runs only (never
the Measurement, which needs the real numbers to classify correctly):

- **pytest-cov**, via `--no-cov` if it's importable — coverage instrumentation is
  pure cost here, because the run already holds coverage and per-Mutant coverage
  is never consumed.
- **pytest-benchmark**, via `--benchmark-disable` if it's importable — benchmark
  timing is unreliable under mutation testing regardless.

`--no-cov` and `--benchmark-disable` are each plugin's own designed-for-this
override, not `-p no:<plugin>`: blocking a plugin outright deregisters its own
options too, so a project's own `addopts = "--cov=..."` would turn into a pytest
"unrecognized arguments" error. Any other plugin is left untouched — some are
load-bearing for correctness, and mutate4py has no way to know which.

The remaining cost is the per-Mutant overhead described under [Timeouts](#timeouts). It
is printed in the **Mutation Report**:

```
Per-Mutant overhead: 0.82s
Hint: per-Mutant overhead is high relative to your test suite; audit pytest
plugins with --pytest-args (e.g. -p no:<plugin>).
```

The hint fires once overhead reaches half of the Measurement's own wall time. To audit
which plugin is responsible, pass `-p no:<plugin>` through `--pytest-args` one
plugin at a time and re-run — that flag *does* fully deregister a plugin, which is
exactly what you want for an audit even though mutate4py can't use it
automatically for the two it neutralises by default.

## Executors

A serial run on a POSIX platform uses the forking executor by default. It primes once: a
fork server (`_worker_server`) imports the project, then forks one child per Mutant, so the
orchestrator's state never reaches a Mutant. Each child runs its Mutant one of three ways:

- by **fresh import** of the mutated module;
- in **swap mode**, for a file the prime already imported (a conftest, a plugin, or an app
  module under Django): the child swaps the mutated function bodies into the live
  functions and runs pytest in-process. A Mutant that swap mode refuses runs in a fresh
  interpreter instead;
- in a **fresh interpreter**, for a Mutant in the harness module, the server's own executor
  and protocol code, which a swap would change under the report.

The **subprocess executor** runs one fresh `pytest` process per Mutant. `--no-fork` forces
it. It is also the whole-run fallback wherever forking is impossible or unsafe (no
`os.fork`, pytest not importable, a fork-unsafe plugin such as tach), and it runs every
Survivor confirmation. The `Executor:` line in the report says which ran, and how many
Mutants ran each way. See [ADR 0028](docs/adr/0028-fork-server-harness-mode-and-swap-mode.md).

## Django projects

Parallel Workers (`--max-workers`) each get their own test database automatically:
mutate4py supplies pytest-django with the per-Worker identity it normally only gets
from pytest-xdist, so no `conftest.py` change is required and Workers never collide
on one test database during migration.

Pass pytest-django's own `--reuse-db` through `--pytest-args` if you want it —
mutate4py can't turn it on for you, because it changes what's on disk between runs
(a kept-around test database) in a way only you can judge safe for your project and
environment:

```bash
mutate4py polls/models.py --max-workers 4 --pytest-args="-q --reuse-db"
```

A migration-signal count in your terminal is not evidence that `--reuse-db` skipped
migrations: pytest-django still runs migrations to create (or verify) each test
database, reused or not. The saving from reuse is skipping the *teardown and
recreation* at the end of the run, not the migration step itself.

Framework bootstrap (`django.setup()`) runs once, before any Mutant, and imports every
`INSTALLED_APPS` model module as a side effect. A Mutant in an app-loaded module (e.g.
`models.py`) is therefore already in `sys.modules` when the executor primes, so it runs in
swap mode rather than by fresh import. The Mutant is still classified the same way; only
the route to that verdict differs. A Mutant in a module outside app loading (a plain utility
module Django never imports through `INSTALLED_APPS`) is run by fresh import.

## Removed in 0.3.0

These flags were removed in 0.3.0. Each is refused with exit 2 and a message naming the
flag, so a script that still passes one fails loudly rather than being silently ignored.

| Removed flag | Replacement |
|--------------|-------------|
| `--cov-cmd` | None. The run measures coverage itself (the Measurement, ADR 0027). |
| `--lcov` | None. The run measures coverage itself; no `lcov.info` is read or written. |
| `--reuse-coverage` | None. Each scored run takes its Measurement, and a rerun with nothing changed skips it. |
| `--test-contexts` | None. Selection reads the run's own Measurement and its Test map; there is no db to pass. |
| `--build-test-contexts` | None. No test-context db is built. |
| `--since-last-run` | None. A default run already re-scores only the changed functions. |
| `--lines` | Edit a function to re-score it, or pass `--mutate-all` for a full re-score. |

Coverage now comes from the coverage.py dependency (`coverage>=7.10`), which the run
drives itself.

## Worker provisioning cost and when parallelism pays off

Each parallel Worker (`--max-workers >= 2`) is a full tree copy of the working
directory, provisioned with `uv venv`/`uv sync` so its editable install resolves
to its own copy (see "How it differs from mutate4go" below). That provisioning
cost is paid **once per Worker per run**, not once per Mutant — so it's fixed
overhead that a run's total Site count must amortize.

For a handful of selected Sites, that fixed cost can exceed what parallelism
saves; for a target file with many selected Sites, splitting the work across
Workers wins even after paying it. There's no universal threshold — it depends on
your test suite's own per-invocation cost — so if `--max-workers` isn't paying
off, check the `Mutation workers: <n>` line against the `Selected mutation
sites:` count in the run header and compare a serial run's wall time against a
parallel one before assuming parallelism should always be on.

## Develop

Python ≥ 3.11, packaged with `hatchling`. The one runtime dependency is coverage.py
(`coverage>=7.10`).

```bash
uv sync
uv run mutate4py --help
uv run pytest
```

## How it differs from mutate4go (`[PY]`)

- **`--max-workers` uses clone-per-worker, not tree-copy+`cwd`** — mutate4go's
  tree-copy model is unsound under Python editable installs (`pip install -e .`), so
  each worker gets its own `uv`-provisioned venv instead.
- **Coverage is measured by the run itself** — there is no coverage flag to pass
  (Python has no universal `-coverprofile` equivalent to hand in).
- **Manifest hash is structural** (`ast.unparse()`), so reformatting and comment edits
  don't trigger a re-test, but any behavior-affecting edit does.
- **Operators are localized** to Python: adds `and`/`or`, `True`/`False`, and the
  identity/membership negation flips `is`/`is not` and `in`/`not in`.
