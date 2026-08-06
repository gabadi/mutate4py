# 02 — check.sh mutation gate uses --test-contexts

**What to build:** `check.sh`'s mutation sample step (the `_cmd.py`-against-full-suite gate) scopes each mutant's test run to only the tests covering that mutant, the same way `perf.sh` already does with `--test-contexts .coverage`. Today `check.sh` runs `uv run mutate4py src/mutate4py/_cmd.py --lcov lcov.info --mutate-all` with no `--test-contexts`, so every mutant reruns the entire pytest suite.

**Blocked by:** None — can start immediately.

## Baseline metrics (measured 2026-08-05, this repo, this machine)

Full suite: `uv run pytest --cov --cov-context=test --cov-report=lcov:lcov.info -q` → **686 tests, 31.78s** reported / 34.5s wall.

`_cmd.py` has 4 covered mutation sites. Mutating it end-to-end (1 baseline run + 4 mutant runs, 5 full-suite executions total):

| Mode | Command | Wall time | Raw stdout |
|---|---|---|---|
| Baseline (today, no `--test-contexts`) | `mutate4py src/mutate4py/_cmd.py --lcov lcov.info --mutate-all` | **2:27.70 (147.7s)** | 836 chars / 23 lines |
| Fixed (`--test-contexts`) | `mutate4py src/mutate4py/_cmd.py --lcov lcov.info --mutate-all --test-contexts .coverage` | **30.07s** | 775 chars / 22 lines |

**→ 4.9x wall-time reduction** on this file. This scales with `(site count) × (full-suite duration)` vs `(site count) × (scoped-test duration)` — the gap widens on larger files / slower suites (this repo's full mutation surface is 346 sites across `src/`).

- [ ] `check.sh`'s mutation step passes `--test-contexts .coverage`, sourced from a `--cov-context=test` run in the preceding Tests gate (mirroring `perf.sh`)
- [ ] Re-run the exact baseline command above post-change and record the new wall time in the PR/commit — target: within ~10% of the 30.07s figure above (not a full-suite-per-mutant regression)
- [ ] Gate still reports the same Killed/Survived/Uncovered counts as the baseline run (4 killed / 0 survived / 2 uncovered) — no silent loss of signal from over-narrow test selection
