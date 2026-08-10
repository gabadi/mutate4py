# macOS CI matrix and POSIX platform declaration — rejected

**Status:** rejected
**Proposed:** 2026-08-10, issue "02 — ADR, POSIX declaration, and macOS in CI"
**Feature:** none — proposal, not shipped (reverted same day, commit 657c121)

## Proposal

Record a target "single execution model" ADR (one Run loop; narrowing, the warm
forking executor, and Worker count each moved to their own scope so today's
mutually-exclusive guards in `_run_prep.py` become unrepresentable), amend ADR
0012/0013/0015/0018 to point at it, backfill an ADR for the forking execution path
(`_fork_server.py`, shipped in #25/#26 with none), declare POSIX support (Linux and
macOS, not Windows) in `pyproject.toml` classifiers and the README, and add
`macos-latest` to the CI matrix so the platform claim is CI-verified rather than
merely asserted.

## Why rejected

mutate4py ships as a single pure-Python wheel/sdist. `.github/workflows/release.yml`
builds with `uv build` and publishes from `ubuntu-latest` only; there is no
compiled extension and no platform-specific wheel tag, so there is no release-side
reason to test on macOS. This is exactly the packaging model `docs/spec.md` §1
already argues for ("a mutation tool ... runs in the project's own toolchain ... a
native binary buys nothing") — one artifact serves every platform regardless of
which OS built it.

The remaining reason to test macOS was purely defensive: catching, before a user
does, the class of macOS-only fork hazard where the Objective-C runtime aborts a
process that touches it after `fork()` — the reason CPython defaults
`multiprocessing` to `spawn` on macOS. That is a real hazard class, but doubling
the CI gate set's runtime and adding OS-conditional plumbing (lcov via
apt-vs-brew, an arch-specific `drywall` asset, etc.) to guard against a hazard
that has never actually been observed in this project was not judged worth the
ongoing cost. The forking executor already gates on `hasattr(os, "fork")`
(`_fork_server.py::is_available`) and falls back to the always-correct subprocess
model wherever forking isn't safe or available — POSIX support is already true by
construction, not something dedicated CI is required to prove.

**Considered and rejected further:**

- Shipping the POSIX declaration (classifiers + README) without the CI matrix —
  rejected as inconsistent with the proposal's own premise: an asserted-but-
  unverified platform claim is exactly the "asserted, not tested" gap the proposal
  existed to close in the first place. Making the claim without the verification
  would recreate that gap rather than close it.
- Landing the ADR/glossary/backfill documentation alone, with no platform claim —
  not pursued here (the whole ticket was reverted together for coherence), but a
  reasonable smaller ticket to revisit later if the single-execution-model target
  architecture is wanted documented independent of the CI/platform question.

## Note for any future attempt

Don't recreate `docs/glossary.md` if this is revisited. This project already tried
a standalone glossary file once — see `.agents/backlog.md`'s 2026-06-28 entry — and
deleted it (commit `e033f6f`) in favor of `CONTEXT.md`'s `## Glossary` section,
specifically because an unlinked second glossary file drifts from the canonical
one. Any new glossary terms (`test-executor`, `priming-depth`, if the
single-execution-model documentation is redone) belong in `CONTEXT.md`, not a new
`docs/glossary.md`.

## Consequences

- CI stays Linux-only; no `macos-latest` leg.
- No POSIX platform metadata or claims added to `pyproject.toml` or `README.md`.
- The execution-model re-scoping itself (issues 03/04, blocked on this ticket) is
  not blocked by this rejection — those can proceed once the target model is
  decided some other way, or once a narrower documentation-only ticket (see above)
  lands.
