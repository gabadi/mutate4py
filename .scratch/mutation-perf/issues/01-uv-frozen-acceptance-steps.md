# 01 — uv run --frozen in acceptance step CLI wrappers — CLOSED, no-op

**Verdict: do not implement.** Re-measured end-to-end against the real `gherkin-mutator` pipeline (the earlier attempt in this file's history couldn't get `gherkin-parser`/`gherkin-mutator` running at all — that was a local `/tmp/aps-build` classpath issue, now fixed by re-cloning). `--frozen` makes no measurable difference; the backlog's "~10s/mutation from uv re-provisioning" claim (`.agents/backlog.md`, 2026-06-28) does not hold up today.

## Method

Added `--frozen` to every `["uv", "run", ...]` call under `acceptance/steps/*.py` (`step_lib.py`, `run_loop_helpers.py`, `run_loop_steps.py`, `coverage_qa_steps.py`, `coverage_steps.py`, `cli_surface_steps.py`, `cli_surface_qa_steps.py`, `run_loop_qa_steps.py`, `parallel_workers_steps.py`, `parallel_workers_qa_steps.py`). Ran the real `site-discovery` feature (70 mutation sites) through `gherkin-mutator --workers 4 --level full` (bypassing the differential/manifest skip so every run does full work), 3x before and 3x after, same machine, back to back.

## Results (wall time, `--workers 4`, 70 mutations)

| Run | No `--frozen` | With `--frozen` |
|---|---|---|
| 1 | 20.93s | 27.09s |
| 2 | 23.16s | 21.09s |
| 3 | 24.22s | 23.23s |
| **avg** | **22.77s** | **23.80s** |

CPU time (user+sys, less sensitive to scheduler noise than wall time) is effectively identical: ~34.6–35.2s before vs ~35.6–36.5s after. The ~4.5% wall-time delta is within run-to-run noise and in the wrong direction to call it an improvement.

`total=70 killed=70 survived=0 errors=0` in every run — no signal loss either way, consistent with a no-op.

## Conclusion

Per this ticket's own acceptance bar ("if the delta is small (<20%), close this out as 'backlog claim was stale' rather than merging a no-op change"): closing as stale. `--frozen` edits were applied, measured, and reverted — not merged. The 2026-06-28 backlog complaint no longer reflects reality (or never did under this repo's actual concurrency/`uv` cache-hit profile) and should not block or motivate further work in this direction.

- [x] Got `gherkin-parser`/`gherkin-mutator` runnable end-to-end (fixed by re-cloning `Acceptance-Pipeline-Specification` into `/tmp/aps-build`, which had been cleared)
- [x] Timed one real feature's mutation run before any change (`site-discovery`, 70 sites, `--level full`, 3x): avg 22.77s wall
- [x] Added `--frozen` to every `uv run` call in `acceptance/steps/*.py`, re-ran same feature 3x: avg 23.80s wall — no improvement
- [x] Reported actual before/after numbers; delta (~4.5%, and negative) is well under the 20% bar — closed as stale, no-op change not merged
