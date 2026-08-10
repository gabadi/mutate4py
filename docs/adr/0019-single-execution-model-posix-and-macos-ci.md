# One Run loop, three levers each at its own scope; POSIX declared, macOS in CI

**Status:** accepted
**Feature:** F7 (execution-model re-scoping, issues #40–#44) · **Spec:** §2, §7, §9
**Amends:** ADR 0012 (serial-only run-loop premise), ADR 0013 (`--max-workers` flag
decision), ADR 0015 (clone-per-worker provisioning), ADR 0018 (mode-related parts
only)
**Backfills:** the forking execution path (issue #25/#26, commit `62595fa`), which
shipped with no ADR and no glossary entry

## Context

mutate4py has three independent speed levers:

1. **Narrowing** — `--test-contexts`, which turns a **Mutant**'s test run into a
   named subset instead of the full suite (ADR 0018).
2. **The warm forking executor** — a primed `pytest.main()` reused across forked
   children instead of one cold subprocess per Mutant (issue #25/#26, undocumented
   until this ADR — see "Backfill" below).
3. **Parallel Workers** — `--max-workers`, N isolated copies of the project running
   Mutants concurrently (ADR 0013/0015).

Each lever was wired in at **run scope** — one flag, one run-wide decision — because
each was built as its own feature slice, against whatever the run loop looked like
at the time. That made every pairwise combination of levers a question the run loop
had to answer, and the honest answer was usually "no":

- `_fork_server_eligible` (`_run_prep.py`) refuses the forking executor whenever a
  Test-context db is in play (narrowing sends a different argument list per Mutant;
  the forking executor replays one fixed argument list captured at prime time) *or*
  whenever the parallel path is taken (a Worker's tree copy is a different process
  entirely; nothing there is primed).
- `_setup_test_context_db` forces `effective_max_workers` to 0 whenever narrowing is
  requested and `--max-workers >= 2` (`_run_prep.py`): narrowing silently downgrades
  a parallel request to serial.

Two guards, one silent downgrade, and a forking executor that is mutually exclusive
with both of the other levers. **This was never a considered trade** — nobody
decided that narrowing and warm execution shouldn't compose. It is the mechanical
consequence of three levers implemented at the same scope (the run) when their
natural scopes are three different things: narrowing is a property of a **Mutant**
dispatch, the warm executor is a property of a **Worker**, and the Worker count is
the one lever that actually belongs at run scope. Flattening three scopes onto one
run-wide mode switch necessarily produces a mutually exclusive cross-product — that
is what a mode switch *is*. It was never going to compose by accident.

## Decision

**One Run loop. Each lever moves to its natural scope:**

| Lever | Old scope | New scope |
|---|---|---|
| Narrowing (Selection outcome) | run-wide fixed command | per-**Mutant** argument list, derived from that **Site**'s Selection outcome |
| Warm execution | run-wide eligibility gate | per-**Worker** property — each Worker provisions and owns exactly one **test-executor**, primed once, alive for the run |
| Worker count | run-wide flag | unchanged — this was already the correct scope |

This is a re-scoping, not an integration layer bolted across the three existing
gates. That distinction matters for what happens to the exclusion guards: an
integration layer would *relax* them (teach `_fork_server_eligible` to tolerate a
Test-context db). Re-scoping instead removes the shared state the guards exist to
protect. `_fork_server_eligible` exists because a single run-wide forking executor
cannot honor a per-Mutant argument list — but once the executor is a per-Worker
property that receives a fresh argument list on every dispatch (a request/response
protocol, not "replay the one command captured at prime time"), there is no fixed
command left for narrowing to conflict with. Same for the Worker-count guard: it
exists because "serial forking" and "parallel tree-copy" used to be two different
code paths that could not both be the active one — once every Worker (including a
single one, on `--max-workers` unset) owns its own executor uniformly, "serial" is
just the one-Worker case of the same mechanism, not a separate path to choose
between.

So the four guards — the no-Test-context-db eligibility condition, the
not-parallel eligibility condition, the silent Worker-count clamp, and the CLI
rejection of the flag pair — do not get relaxed. They become **unrepresentable**:
there is no longer a code path where two levers' state could disagree, so there is
nothing left to guard. (Deleting the guards themselves, and the executor-interface
and dispatch-protocol changes that make them unrepresentable, is the work of
issues #41–#43; this ADR records the decision and the scoping it rests on before
that code moves.)

Degradation stays per-axis, not global: if the warm executor is unsafe for one
target file (module leak, non-`pytest` command, non-POSIX host), that file's
Worker(s) fall back to the subprocess executor while narrowing and parallelism keep
working — because those are properties of different scopes and don't have to fail
together.

## Amendment — ADR 0012 (serial-only run-loop premise)

ADR 0012 records the *observable output tokens* of the run loop (the
`Mutation workers:` header line, the `worker-<k>` per-mutant token) as a function
of `--max-workers` and selected-site count. **That contract is unchanged by this
ADR and remains authoritative.** What ADR 0012 does not speak to, and this ADR
supersedes by omission, is any assumption that "serial" and "parallel" are two
different *execution engines* selected once per run. After the re-scoping, serial
is the one-Worker case of a single Worker-dispatch mechanism, not a separate
branch — but which executor a Worker holds (forking vs subprocess) and how many
Workers exist are now orthogonal facts, neither of which the output-token rules
depend on. The token rules stay keyed to Worker count and site count exactly as
ADR 0012 describes.

## Amendment — ADR 0013 (`--max-workers` restored as a real flag)

ADR 0013's decision — `--max-workers` is a real, validated, run-scoped flag, and
the only usage error is combining it with `--scan`/`--update-manifest` — is
**unchanged and reaffirmed**: the Worker count is the one lever that was already at
its correct scope. What this ADR withdraws is the *fourth* guard layered on top of
it since: the CLI rejecting `--test-contexts` together with `--max-workers >= 2`.
That guard was never part of ADR 0013's decision; it was added later, at the same
run-wide-mode-switch layer this ADR is dismantling, and is deleted alongside the
other three (issue #43).

## Amendment — ADR 0015 (clone-per-worker via `uv`)

ADR 0015's provisioning mechanism — a tree copy per Worker, `uv venv`/`uv sync`,
the user's test command run verbatim with `cwd = worker-root` — is **unchanged**.
It turns out to already be the right home for the warm executor: "each Worker
provisions and owns exactly one executor, primed once" (this ADR's table, row 2)
is additive to a Worker's existing responsibilities, not a competing mechanism.
A Worker's tree copy is where a forking executor's priming pass (import
`conftest.py`, run framework bootstrap) now happens once per Worker instead of
once per run — the same clone-per-worker isolation ADR 0015 already established
for correctness (editable-install soundness) also gives each Worker's primed
executor its own resolved, non-conflicting environment for free.

## Amendment — ADR 0018 (`--test-contexts` selection, mode-related parts only)

**The three-case model itself is authoritative and unchanged by this ADR:**
`narrowed` / `static` / disagreement (`line-absent` / `file-absent`, exit 2, no
`Mutation Report`) remain exactly as ADR 0018 defines them, including the
`Test selection: narrowed <n>, static <k>` report line and the query-before-splice
ordering. Nothing about *how a Site's outcome is classified* changes here.

What this ADR amends is the one sentence describing *what the run loop does with
narrowed vs. static*: ADR 0018 says "Because `--test-contexts` already forces
serial execution (`_setup_test_context_db`), this is a serial-path-only change."
That forcing rule is a run-wide-mode-switch artifact of the kind this ADR
dismantles — once narrowing is a per-Mutant argument list handed to whichever
Worker a Site is dispatched to, forcing the whole run serial is no longer required
for narrowing to be honored correctly. The forced-serial guard is deleted (issue
#43, tracked as the silent Worker-count clamp above), not relaxed into a partial
rule. Everything else in ADR 0018 — the classification, the abort behavior, the
report line, the combined-db model for batches — stands as written.

## Backfill — the forking execution path (issue #25/#26, no prior ADR)

`_fork_server.py` shipped (commit `62595fa`) without an ADR or a glossary entry.
Recorded here retroactively, alongside the POSIX declaration it motivates:

**What it does.** A parent process primes pytest once per run — a `--collect-only`
pass against an empty scratch directory *inside* the working tree (so root
`conftest.py` and any framework bootstrap it runs, e.g. `django.setup()`, execute
without importing any real test file) — then `os.fork()`s a child per Mutant. Each
child calls `pytest.main()` in-process against the mutated on-disk file, classifies
the result, and `os._exit()`s; the parent never imports the guarded target itself
(`assert_source_clean` enforces this after priming — a fork inherits the parent's
`sys.modules`, so a pre-imported target would make every child test pre-mutation
code and every Mutant would falsely survive). This is strictly an *optimization*:
`is_available`/`prime()` failure of any kind falls back to the existing per-mutant
subprocess model rather than erroring, because correctness must never depend on
the fast path being available.

**POSIX by construction.** `is_available` gates on `hasattr(os, "fork")` — Windows
CPython has no `os.fork`, so the forking executor is already structurally
unreachable there; it has never been reachable, silently, since it shipped. This
ADR makes that an explicit, documented platform contract instead of an
implementation accident (see "Platform declaration" below).

**The macOS hazard this ADR's CI change exists to catch.** macOS's Objective-C
runtime aborts a process that calls into it after a `fork()` in a parent that has
threads — the reason CPython made `spawn` the default `multiprocessing` start
method on macOS in 3.8 (bpo-33725), rather than `fork` as on Linux. mutate4py's
forking executor is not `multiprocessing` and does not itself spawn threads, but it
forks *after* priming pytest — and pytest's own collection, plugin loading, and any
project `conftest.py`/framework bootstrap run inside that priming step, arbitrarily,
in a process this tool does not control. Any of that machinery touching a
thread-backed macOS framework (e.g. networking or DNS resolution routed through
system `CoreFoundation`/`Foundation` APIs, common in SSL and some database
drivers) before the fork point reproduces the same hazard class, silently, on the
one platform where fork has this restriction and Linux does not. A CI history that
has only ever run on Linux cannot see this class of failure at all — it is not a
theoretical gap, it is exactly the gap this ADR closes by putting macOS in CI
(see below) instead of trusting "POSIX" to mean "tested."

## Platform declaration

The project has carried no operating-system metadata and has never run CI on
anything but Linux, despite being developed on macOS and shipping a POSIX-only
execution path. This ADR makes the supported platform set explicit where a user
sees it before installing:

- **Package metadata** (`pyproject.toml` `classifiers`) declares
  `Operating System :: POSIX`, `Operating System :: POSIX :: Linux`, and
  `Operating System :: MacOS :: MacOS X`. No Windows classifier is added.
- **README** states the same thing in prose: Linux and macOS are supported;
  Windows is not, because the forking execution path requires `os.fork`.
- **CI** runs the full gate set — lint, format, tests (including the forking
  path's own test suite), CRAP, DRY, manifest check, and acceptance — on both
  `ubuntu-latest` and `macos-latest`, matrixed, so the platform claim is verified
  on every change rather than asserted once and left to rot.

**Considered and rejected:** Windows support via the subprocess-only fallback
(the forking executor already degrades gracefully there) — rejected because the
project has never tested on Windows at all, and a platform classifier is a claim
about what is *verified*, not about what might incidentally work; revisit only
alongside actual Windows CI. Declaring POSIX support without adding macOS to CI —
rejected as the exact "asserted, not tested" gap this ADR exists to close.

## Glossary additions

Two terms this ADR's vocabulary depends on, added to `docs/glossary.md`:

- **test-executor** — the primed-once, run-many abstraction both the forking and
  subprocess models implement: prime once, then given an argument list and a
  timeout, run it and return a classification. Formalizing this as one interface
  (rather than the run loop branching on which model it has) is what makes "each
  Worker owns exactly one executor" representable; the interface itself is
  introduced in issue #41, but the concept — and the rename from "fork server" to
  "executor" it carries — is named here because this ADR's re-scoping is stated in
  those terms.
- **priming-depth** — how much of the test framework's bootstrap a test-executor
  runs once at prime time versus repeats per Mutant. Today's forking executor's
  priming depth is a full `pytest --collect-only` pass: it imports every
  `conftest.py` and runs whatever framework setup collection triggers (e.g.
  `django.setup()`), before the first fork. A shallower priming depth — importing
  pytest without running its configuration/collection, so framework bootstrap
  never happens before a mutant-specific run — is an open question, not yet
  measured (tracked as a follow-up in issue #44).

## Consequences

- The re-scoping described here is a decision, not yet code: the four guards named
  above still exist in `_run_prep.py` after this ADR lands, and are deleted in
  issues #41–#43 once the executor interface and per-Worker dispatch protocol they
  depend on exist. This ADR is what those tickets implement against.
- CI cost roughly doubles (two OS legs instead of one) in exchange for the forking
  path's macOS-specific hazard class becoming something CI can actually catch.
- A future contributor proposing "add a mode switch to let X and Y combine" should
  find this ADR first: the answer this project settled on is not a switch, it is
  putting each lever at the scope where it never had to switch at all.
