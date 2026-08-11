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

**FunctionID**:
The Function unit id attributed to a Site by line range. Empty for module-level
Sites, which are still mutated.

### Manifest

**Manifest**:
The per-file record of each Function unit's structural hash at the time it was last
mutation-tested, letting a later run tell which units changed. Embedded in the
source footer by default, or a sidecar JSON file.
_Avoid_: cache, state file, lockfile

**Unit hash**:
A Function unit's structural fingerprint. Reformatting and comment edits leave it
alone; behaviour-affecting edits change it.

**Differential rerun**:
Re-testing only the Sites whose Function unit changed since the last Manifest. The
default once a Manifest exists.

### Coverage

**Coverage gate**:
The line-coverage filter that splits discovered Sites into covered and uncovered.
Branch data is deliberately ignored.
_Avoid_: coverage filter, eligibility check

**covered / uncovered**:
The two disjoint, exhaustive partitions of the discovered Sites.

**Baseline**:
One run of the test suite against unmutated source. It must pass, and its duration
sets the Mutant timeout.

### Execution

**Executor**:
The interface both Mutant-execution backends implement — prime once, then run a test
argument list under a timeout and classify. The forking executor is the fast path;
the subprocess executor is the always-correct fallback.

**Worker**:
An isolated tree copy of the working directory with its own provisioned environment,
mutating its own file copy. Parallelism unit.
_Avoid_: thread, process, job

**Selected sites**:
The covered Sites actually mutated, after line filtering and differential selection.

**Classification**:
The per-Site verdict: **killed**, **survived**, or **timeout**. Timeout is visible
per-Mutant and counted as killed in the report.
_Avoid_: result, status, outcome (reserve *outcome* for Selection outcome)

### Test selection

**Selection outcome**:
What the test-context db says about a Site's line — **narrowed** (named tests cover
it, so only those run), **static** (import-time code no single test owns, so the
full test set runs), or a disagreement.

**Empty context**:
Coverage.py's whole-run context, as opposed to a named per-test one. A line matched
only by it ran at import time. A signal, not noise.

**Selection disagreement**:
The test-context db and the Coverage gate contradicting each other. Always an input
defect — a stale db or a path mismatch — never uncovered code, so it aborts the run
rather than falling back.
