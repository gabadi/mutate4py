# 01 — uv run --frozen in acceptance step CLI wrappers

**What to build:** Acceptance-step CLI invocations (`acceptance/steps/step_lib.py`: `run_mutate4py`, `check_cli_available`, `run_cli`, plus any other `["uv", "run", ...]` call under `acceptance/steps/*.py`) skip uv's per-invocation lock/sync check via `--frozen`. This targets the backlog's own logged complaint (`.agents/backlog.md`, 2026-06-28, hardender): *"uv re-provisioning per Gherkin mutation makes acceptance mutation slow (~10s/mutation)"* — a claim that has never been re-measured since it was logged.

**Blocked by:** None — can start immediately.

## Baseline metrics (measured 2026-08-05, this repo/machine) — inconclusive, needs re-validation

This sandbox could not run the real `gherkin-mutator` pipeline against a feature (`gherkin-parser` failed here with a babashka classpath error unrelated to this repo — likely a local tool-install issue, not a code issue), so the ~10s/mutation claim could **not** be reproduced end-to-end. As a proxy, concurrent `uv run` invocations were timed directly:

| Concurrency | Command | No `--frozen` | With `--frozen` | Delta |
|---|---|---|---|---|
| 12-way | `uv run python -c "pass"` | 2.141s | 2.388s | ~0 (noise, slightly worse) |
| 24-way | `uv run mutate4py --help` | 3.607s | 3.293s | ~9% faster |

This is a **weak, inconclusive signal** — nowhere near the "~10s/mutation" the backlog describes. Either (a) the real contention only shows up under the actual `gherkin-mutator` worker harness (heavier subprocess tree, real venv state, this machine's disk/CPU under load) and this proxy undersells it, or (b) the backlog claim is stale/no longer the actual bottleneck and the real cost is elsewhere in the acceptance entrypoint. **Do not implement `--frozen` blind** — measure first.

- [ ] Get `gherkin-parser`/`gherkin-mutator` runnable end-to-end in a real dev environment (fix whatever broke here, or use the working swarm worktree setup)
- [ ] Time one real feature's mutation run (`acceptance/run_gherkin_mutation.sh` scoped to a single stem, e.g. `site-discovery`) before any change — record wall time and per-mutation average from the tool's own timing output
- [ ] Add `--frozen` to every `uv run` call in `acceptance/steps/*.py`, re-run the same feature, record the new wall time and per-mutation average
- [ ] Report the actual before/after numbers (not the proxy above) in the PR; if the delta is small (<20%), close this out as "backlog claim was stale" rather than merging a no-op change
