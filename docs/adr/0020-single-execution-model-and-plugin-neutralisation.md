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

## Amended: the fork server and swap mode replace the leak fallback (2026-11-13)

A target leaking into `sys.modules` at prime is no longer a fallback reason. The
forking executor primes in a fork server, never in the orchestrator, and runs a
file prime loaded in swap mode, or one of the server's own modules in harness
mode, with a per-Mutant fresh interpreter for anything a body swap cannot
express (ADR 0028). The fork-unsafe plugin guard now covers Mutant runs: a
prime session that registers tach gives the subprocess executor, which states
why. The remaining whole-run fallbacks are no `os.fork`, pytest not importable,
`--no-fork` and a fork-unsafe plugin.

## Amended: `--no-cov` needs pytest-cov loaded in the child, not only importable (2026-11-15, #127)

"Importable" was the wrong test for pytest-cov. `--no-cov` is an option pytest-cov
registers, so the flag is a pytest usage error (exit 4, "unrecognized arguments:
--no-cov") in any pytest that does not load the plugin. With
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` pytest loads only the plugins that are named, so a
run that left pytest-cov unnamed failed its Measurement at the Baseline even though
`pytest_cov` was importable.

`neutralising_args(pytest_args)` now adds `--no-cov` only when both hold: `pytest_cov`
is importable, and the child session will load it. That is when autoload is on (the
switch is unset or empty), or when `-p pytest_cov` / `-p pytest_cov.plugin` (also the
`-ppytest_cov` spelling) appears in the pytest args of that session or in
`PYTEST_ADDOPTS`. Each caller passes the args of the session it is building: the run's
pytest args for the Measurement and for every Mutant, the forking executor's prime args
for its prime, and each request's own args in a Worker (the Worker reads its own
environment).

Rejected: catching the exit-4 and retrying without the flag (the Baseline would run
twice, and a real usage error would be swallowed); passing `-p pytest_cov` ourselves
when autoload is off (it would load a plugin the user chose not to load, and registers
it under a second name if they name `pytest_cov.plugin`); and `-p no:pytest_cov`, for the
reasons above. A pytest-cov named only by an ini `addopts` is not detected, so such a
run with autoload off gets no `--no-cov`.

pytest-benchmark keeps its importable-only guard. Its `--benchmark-disable` has the same
shape of failure under autoload off, and is left to a separate change.
