# One `Executor` interface; plugins disabled by kill switch, not by `-p no:`

**Status:** accepted

Mutant execution has two backends behind one `Executor` protocol (prime once, then
run an argument list under a timeout and classify). The **forking executor** primes
pytest once and forks per Mutant; the **subprocess executor** runs a fresh
`python -m pytest` per Mutant. Serial runs and each parallel Worker both hold
exactly one primed Executor and never branch on which.

**The forking executor degrades silently, never hard-errors.** Wrong platform,
pytest not importable, or the target leaking into `sys.modules` during priming all
fall back to the subprocess executor. It is a best-effort accelerator, not a
correctness-affecting choice — so eligibility is a property of *this interpreter's*
import state, decided once per process that attempts it.

## Why `--no-cov` and not `-p no:pytest_cov`

Two plugins are neutralised on **Mutant runs only** (never the Baseline, which needs
real numbers to classify): pytest-cov via `--no-cov`, pytest-benchmark via
`--benchmark-disable`. Per-Mutant coverage is never consumed — the run already holds
coverage acquired up front — and benchmark timing is meaningless under mutation.

Each uses the plugin's **own kill switch** rather than blocking it outright.
`-p no:<name>` prevents the plugin registering its options at all, so a project's
own `addopts = "--cov=..."` becomes a pytest "unrecognized arguments" error. The
kill switch is built for this override and leaves the option registered.

Each flag is added only when its plugin is actually importable, because both are
pytest usage errors when it isn't.

**No other plugin is touched.** Some are load-bearing for correctness and this layer
cannot tell which. Remaining per-Mutant plugin cost is measured once at Baseline
with a `--collect-only` pass and reported as `Per-Mutant overhead`, with a hint to
audit via `-p no:<plugin>` in `--pytest-args` — which is correct for a *manual*
audit even though the tool can't use it automatically.

## Superseded in part: the `--collect-only` overhead probe (2026-11-13)

The per-Mutant overhead is no longer measured by a `--collect-only` pass. It is
derived from the single ctrace pytest session that builds the Measurement (ADR
0027): wall time minus the summed test durations, floored at 0, printed once per
run. The rest of this ADR still holds, including the rule that no other plugin is
touched and the `-p no:<plugin>` audit hint.
