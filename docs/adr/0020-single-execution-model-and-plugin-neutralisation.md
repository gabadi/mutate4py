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

## Amended: a kill switch is dropped only when the child provably does not load its plugin (2026-11-15, #127)

"Importable" was the wrong test. `--no-cov` is an option pytest-cov registers, so the flag
is a pytest usage error (exit 4, "unrecognized arguments: --no-cov") in any pytest that
does not load the plugin. With `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` pytest loads only the
plugins that are named, so a run that left pytest-cov unnamed failed its Measurement at the
Baseline even though `pytest_cov` was importable. `-p no:pytest_cov` fails the same way with
autoload on. The same holds for pytest-benchmark's `--benchmark-disable`.

The opposite mistake is worse. A pytest-cov that the child does load, and that is not told
`--no-cov`, starts its own Coverage and pauses the Measurement's collector: every Mutant is
scored Uncovered and the run exits 0. That is a wrong score nothing flags, where a wrong
`--no-cov` is a loud exit 4. A first version of this amendment decided "loaded" from the
session args and `PYTEST_ADDOPTS` alone, and so dropped the switch for a project whose ini
`addopts` is `-p pytest_cov --cov=calc` under autoload off.

**The rule: when unsure, keep the switch.** Missing a source must end in a loud exit 4, never
in a silent wrong score. `neutralising_args(pytest_args, cwd=...)` adds a plugin's switch
when its module is importable, unless the child provably does not load the plugin. The child
does not load it only when nothing names it and autoload is off, or when it is blocked:

- **Named** by any of these, as a `-p` value (`-p <name>`, `-p<name>`) or text: the session
  args; `PYTEST_ADDOPTS`; the `addopts` of the inifile; `PYTEST_PLUGINS`; and any conftest
  the run loads, matched as plain text (a conftest that contains the plugin's name counts).
  A named plugin keeps its switch whatever else is set.
- **Autoload off** means `PYTEST_DISABLE_PLUGIN_AUTOLOAD` set and non-empty (as pytest reads
  it), or `--disable-plugin-autoload` in the session args, in `PYTEST_ADDOPTS` or in the
  inifile `addopts`. With autoload on, an unblocked plugin is loaded.
- **Blocked** means `-p no:<entry point>` in the session args, `PYTEST_ADDOPTS` or the
  inifile `addopts`: the plugin is not loaded even with autoload on, unless something names
  it.
- A source that does not parse (an unbalanced quote in `PYTEST_ADDOPTS` or an inifile
  `addopts`) leaves the answer unknown, and unknown keeps the switch.

Where each source is read. The inifile, its `addopts` and the conftests are located the way
the tests digest locates them (`_tests_fingerprint`): the inifile search starts at the run
directory and at the common ancestor of the run's test paths, and the conftests are those
above each collection root up to the inifile's directory plus those beneath it (more than
pytest loads, never fewer). A `-c` file replaces the search, and a command-line
`-o addopts=...` replaces the inifile's value. When several config files in one directory
could be the inifile, the autoload switch must be in all of them to count, and a name in any
of them counts. Autoload off is the claim that drops a switch, so it is read strictly and
every source of a name is read broadly.

Each plugin has its own names, kept in one table (`_KNOWN_PLUGINS`): pytest-cov is named
`pytest_cov` (entry point and module prefix, so `pytest_cov.plugin` too); pytest-benchmark
has the entry point `benchmark` and the module `pytest_benchmark`, whose plugin is
`pytest_benchmark.plugin`. The entry point is what `-p no:` blocks.

Each caller passes the args and directory of the session it is building: the run's pytest
args and cwd for the Measurement and for every Mutant, the forking executor's prime args for
its prime, and each request's own args and the Worker's cwd in a Worker (which also reads
its own environment).

Rejected: catching the exit-4 and retrying without the flag (the Baseline would run twice,
and a real usage error would be swallowed); passing `-p pytest_cov` ourselves when autoload
is off (it would load a plugin the user chose not to load, and registers it under a second
name if they name `pytest_cov.plugin`); `-p no:pytest_cov`, for the reasons above; and
deciding from the session args and `PYTEST_ADDOPTS` only (the silent-Uncovered failure
above). Not read: plugins that a named plugin or a `conftest` loads by another route, a
plugin named by a spelling this module does not know. Those cost a loud exit 4 under autoload
off, never a wrong score.
