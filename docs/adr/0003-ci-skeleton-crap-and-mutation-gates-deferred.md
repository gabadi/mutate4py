# ADR 0003 — CI/CD skeleton: uv-native gates; CRAP & mutation gates deferred

- Status: accepted
- Date: 2026-06-25
- Feature: F1 (`site-discovery`)
- Spec: docs/spec.md §1 (substrate), §11 (build order); constitution local-engineering

## Context

F1 lands a runnable, gated, releasable package, not just an analysis module. CI is
modeled on the Python gold-template sibling `crap4py`'s
`.github/workflows/ci.yml`/`release.yml`, adapted to mutate4py's stack (stdlib
`ast`, zero runtime deps, `uv`/`pytest`/`hatchling`).

The constitution's local-engineering rule and the module-mirror sibling
(`mutate4js` ADR 0003) both establish that **CRAP and mutation gates are deferred**
until the first working implementation and the runner land — before then there is
nothing meaningful for them to score.

## Decision

**`ci.yml`** (single `ubuntu-latest` job, gates in sequence, any failure fails the
check), mirroring crap4py:

1. `ruff check src/ tests/` (lint)
2. `ruff format --check src/ tests/`
3. `pytest --cov --cov-report=lcov:lcov.info --cov-report=term-missing
   --cov-fail-under=<N>` (unit tests + coverage)
4. **DRY gate:** download the `drywall` release binary and run `./drywall src/`.
5. **Commented placeholder** naming where the **CRAP gate** (`crap4py src/ --lcov
   lcov.info --max-crap <N>`) and the **mutation gate** will slot in once F4's
   runner exists. These gates are **deferred in F1**, per the constitution.

**`release.yml`** (on tag `v*.*.*`): `uv build` → publish to PyPI → GitHub release.
Kept in F1 because the user scoped F1 as a "runnable, gated, **releasable**
skeleton" and the crap4py template ships it. (mutate4js deferred release to a later
deliverable; mutate4py does not — a deliberate divergence, justified by the explicit
F1 scope.)

**`.gitignore`:** extend the existing swarm-infra lines with crap4py's Python
artifact patterns (`__pycache__/`, `*.pyc`, `*.pyo`, `.venv/`, `.coverage`,
`coverage.lcov`, `lcov.info`, `*.egg-info/`, `dist/`, `build/`, `.pytest_cache/`,
`acceptance/parsed/`, `acceptance/generated/`) plus this tool's own crash-safety
backup `.mutate4py.bak` (spec §7).

## Consequences

- Green CI from F1 means every later feature merges onto a gated baseline.
- The deferred CRAP/mutation gates are a single commented block to uncomment in F4,
  not a CI rewrite.
- `release.yml` existing early means a tag can cut a (pre-alpha) PyPI release at any
  point; version stays `0.0.0` until intentionally bumped.

## Alternatives considered

- **Enable CRAP/mutation gates in F1** — rejected: nothing to score before the
  runner; contradicts the constitution local-engineering rule and mutate4js ADR
  0003.
- **Defer `release.yml` (mutate4js's choice)** — rejected here: F1 is explicitly
  scoped as releasable and the template provides it cheaply.
- **OS/Python-version matrix** — rejected: a single pinned environment is enough for
  a single-file-at-a-time dev tool (mutate4js ADR 0003 rationale).
