# mutate4py — context & glossary

Mutation testing for Python, distinguished by an **embedded-in-source manifest** so
differential reruns survive a clone with no CI state.

Use these terms in issue titles, test names, and proposals; don't drift to synonyms.
If a concept you need isn't here, that's a signal — either you're inventing language
the project doesn't use, or there's a real gap to record. Behaviour lives in the
code; decisions and their rejected alternatives live in [`docs/adr/`](docs/adr/).

## Language

### Mutation

**Site**:
A single AST location that can be mutated — one operator, one boolean literal, or
one integer `0`/`1`. Yields exactly one Mutant.
_Avoid_: mutation point, target

**Mutant**:
The mutated form of a Site.
_Avoid_: variant, mutation

**Splice / restore**:
Applying a Mutant by byte-offset source edit, then rewriting the original back. The
in-place model: one file on disk, one Mutant at a time.
_Avoid_: patch, inject

**Function unit**:
The granularity the Manifest tracks and differential reruns scope by — a top-level
`def`/`async def` or a method. Nested `def`s and lambdas fold into the enclosing
named unit rather than forming their own.
_Avoid_: function, scope, block

**Class unit**:
A class outside any function, tracked by the Manifest for the Sites of its own body: the
statements, decorators and bases that are not a method or a nested class. Its Manifest
entry has the same `score` block as a Function unit's.

**FunctionID**:
The Function unit id attributed to a Site by line range (`func/<Name>`), or the Class
unit id for a Site in a class body (`class/<Name>`, with the names of its enclosing classes
before it: `class/<Outer>.<Name>`). Empty for module-level Sites,
which are still mutated.

### Manifest

**Manifest**:
The per-file record of each Function unit's structural hash at the time it was last
mutation-tested, letting a later run tell which units changed. Embedded in the
source footer by default, or a sidecar JSON file.
_Avoid_: cache, state file, lockfile

**Unit hash**:
A Function unit's structural fingerprint. Reformatting and comment edits leave it
alone; behaviour-affecting edits change it.

**Tests digest**:
A Function unit's SHA-256 over the test inputs that can reach its covered Sites: the
test files the Measurement shows reaching them, their conftests, the run's support
files (imported helper modules, and every non-Python file under the test folders), the
pytest table of `pyproject.toml`, the pytest ini file and `uv.lock`. Stored
beside the Function unit's score. A stored digest that no longer matches the fresh one
re-scores that unit (ADR 0029).

**Differential rerun**:
Re-testing only the Sites whose Function unit changed since the last Manifest. The
default once a Manifest exists.

**Accepted equivalent**:
A survived Mutant whose Site line carries `# mutate4py: equivalent <reason>`. Recorded
under the Function unit's `accepted` list with its reason; it does not fail the run.
_Avoid_: ignored, suppressed

**Unscored**:
A Function unit with no stored entry, or whose Manifest entry has no `score` (written before
0.1.5, or never scored by a run). A default run scores it. `--check-manifest` judges it on hashes alone.
_Avoid_: clean

### Coverage

**Coverage gate**:
The line-coverage filter that splits discovered Sites into covered and uncovered. It
reads the Measurement's data; a line is covered when any context reached it, Empty
context included. Branch data is deliberately ignored.
_Avoid_: coverage filter, eligibility check

**covered / uncovered**:
The two disjoint, exhaustive partitions of the discovered Sites.

**Run scope**:
The functions a run scores: the changed or Unscored ones in a differential run, every discovered function in a full run. The run header's `Covered mutation sites` and `Uncovered mutation sites` counts and the `Uncovered mutations:` block (one `file:line` per Site) cover the Run scope only.

**Test levels**:
Three levels: `unit` (in-process, coverage-measured, the only tests a scored run's Measurement takes), `system` (real processes: a fork server, worker servers, nested pytest, a spawned interpreter; run by `test-system` without coverage), and acceptance (the Gherkin features). Every test carries exactly one of `unit` or `system` (ADR 0030).
_Avoid_: component test, integration test (both markers are retired)

**Measurement**:
The one pytest session a scored run takes before any Mutant runs: the run's unit tests
in the Project environment, under coverage.py's `ctrace` core, each test in its own
context. Its data gives the Baseline, the Coverage gate and the Test map (ADR 0027).
_Avoid_: coverage run, pre-run

**Baseline**:
The Measurement's pass requirement: the unmutated suite must pass in the Measurement,
or no Mutant runs. The Measurement's wall time gives the Per-Mutant overhead (wall
time minus summed test durations), which is part of every Mutant's timeout.

**Test map**:
The named tests that reached each covered line in the Measurement. Dispatch runs a
Site's narrowed tests from it.
_Avoid_: coverage contexts, test list

### Execution

**Executor**:
The interface both Mutant-execution backends implement — prime once, then run a test
argument list under a timeout and classify. The forking executor runs Mutants from a
Fork server, each by fresh import, Swap mode or a fresh interpreter. The subprocess
executor is the whole-run fallback where forking is impossible or unsafe, and it runs
every Survivor confirmation that the Fork server does not (see Survivor confirmation).

**Fork server**:
The `_worker_server` process the orchestrator starts over the project tree itself, for a
serial run and a parallel one, under the Project environment. It primes the forking executor once and forks one child
per Mutant, so the orchestrator's state never reaches a Mutant.

**Harness module**:
A file loaded before the Fork server primes: part of the server's own code, the executor
and protocol code a child runs around pytest. Each Mutant in it runs in a fresh interpreter,
because a swap would change the code that reports the child's result.

**Swap mode**:
The forking executor's way of running a file the prime imported (a conftest or a
plugin): the forked child swaps the mutated function bodies into the live functions and
runs pytest in-process. A Mutant the swap refuses runs in a fresh interpreter instead.

**Survivor confirmation**:
The re-run of every Survivor with the full test set, before a Survivor is reported. A
run re-runs a fresh-import file's Survivors on the Fork server. Any other file's are
re-run in a fresh interpreter: through the subprocess executor in a serial run, and in a
parallel run by each Worker, in its own clone. A narrowed selection or a swap can let a Mutant
survive that the full test set kills, so a Survivor is not trusted until this run agrees.

**Control run**:
The re-run of a Mutant's pytest argv on the original code, made only when that Mutant
ends in pytest exit 4 or 5. Tests that run (pytest exit 0 or 1) mean the Mutant broke the
run, so it is killed. Any other end (exit 4 or 5 again, a timeout, a crash) means the
argv is the suspect, so the run aborts.

**Worker**:
An isolated tree copy of the working directory with its own provisioned environment,
mutating its own file copy. Parallelism unit.
_Avoid_: thread, process, job

**Import root**:
A symlink-only directory that supplies the `mutate4py` package to a Worker venv as a fallback after site-packages.

**Worker venv**:
`<worker_root>/.venv`, built with `uv sync` pinned to the orchestrator's Python, in which a Worker's server and pytest run.

**Project environment**:
The target project's `.venv`, or a `uv run --with` overlay on it; scored runs must run under it.

**Selected sites**:
The covered Sites actually mutated, after differential selection.

**Classification**:
The per-Site verdict: **killed**, **survived**, or **timeout**. Timeout is visible
per-Mutant and counted as killed in the report.
_Avoid_: result, status, outcome (reserve *outcome* for Selection outcome)

### Test selection

**Selection outcome**:
What the Measurement says about a Site's line — **narrowed** (named tests reach it, so
only those run) or **static** (import-time code no single test owns, or a line no test
reached, so the full test set runs).

**Empty context**:
Coverage.py's whole-run context, as opposed to a named per-test one. A line matched
only by it ran at import time.
