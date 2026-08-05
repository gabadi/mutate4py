# Positional targets become optional, variadic glob patterns, with zero args triggering uv workspace autodiscovery

**Status:** accepted
**Feature:** F5 (cli-surface) · **Spec:** §2 (issue #22)

Issue #22 asked for two related capabilities neither upstream port has any precedent
for: point mutate4py at more than one target in a single invocation, and let it find
its own targets in a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/)
with no target at all. mutate4go and clj-mutate both mutate-test **exactly one file
per invocation** — the caller's shell decides what's in scope, every time. mutate4py
already broke from that model once, for directory mode (ADR-adjacent, spec §2's
`--exclude` rationale); #22 generalizes it: the positional becomes a set of resolved
roots, arrived at by expanding zero or more glob patterns, or by discovering a uv
workspace when none are given. This ADR pins the resulting model so it isn't
re-derived from prose, mirroring why ADR 0008 exists for the coverage flags —
another case of "upstream gives no precedent, so the shape is ours to design."

## 1. The positional becomes optional and variadic; zero args triggers discovery

`file` (singular, required) becomes `files` (`nargs="*"`, zero or more). **Arity,
not a new flag, decides the run shape:**

- **Exactly one** resolved path → today's single-file/directory dispatch,
  byte-for-byte unchanged.
- **Two or more** resolved paths → a union batch: the `.py` files under every root
  are collected, deduped by `os.path.realpath`, and run as **one** baseline and
  **one** exit code (a file failing anywhere fails the run).
- **Zero** → uv workspace autodiscovery (item 3 below). No `--discover`/`--workspace`
  flag; the absence of positionals is the trigger, because a bare `mutate4py` is
  exactly what a developer standing in a workspace root reaches for first.

## 2. One glob dialect everywhere, hand-rolled — why fnmatch was rejected

Positionals are **glob patterns**, expanded with stdlib `glob.glob(pattern,
recursive=True)`, not just literal paths. `--exclude` and (§3 below) uv
`members`/`exclude` all match against strings that are *already* resolved paths, so
they need a **matcher**, not filesystem expansion — and it has to be the *same*
dialect `glob.glob` uses, or a directory kept by one and dropped by the other would
silently disagree.

`_is_excluded` previously used `fnmatch.fnmatchcase`, whose `*` **crosses `/`**
unconditionally and has no `**` concept at all (it's accepted only because `*`
already swallows it). That is a real bug, not a style choice: `--exclude '*/tests/*'`
matched at *any* depth, but so did the accidental `--exclude '*.py'` for *every*
file in the tree, and there was no way to write "at any depth" and "exactly one
level" as two different patterns. `src/mutate4py/_glob_dialect.py` hand-rolls a
small translator instead: `*` matches exactly one path segment (never crosses `/`);
`**` matches zero or more segments, but *only* when it stands alone as a whole
`/`-bounded component — glued to literal text (`foo**bar`) it degrades to an
ordinary same-segment wildcard, which is what stdlib `glob.glob` itself does for
that shape (verified directly against it). `pathlib.PurePath.full_match` ships this
exact dialect natively, but only from 3.13; the translator is ~40 lines, not a
general glob engine, and it is the one piece of matching logic every
pattern-consuming surface in #22 shares.

## 3. Workspace root walked recursively; members are additive

Autodiscovery climbs from `cwd` (inclusive) to the nearest ancestor `pyproject.toml`
and requires it to declare `[tool.uv.workspace]` — mirroring uv's own
`find_workspace`, stdlib `tomllib` only, never a `uv` subprocess (§5 below). Roots =
the workspace root directory, walked recursively exactly like directory mode always
has, **plus** every directory matched by `[tool.uv.workspace].members` globs that
has its own `pyproject.toml`. Root order is workspace root first, then members, in
declaration order — the same "no global re-sort" ordering directory mode already
had, just applied across more than one root.

## 4. uv `exclude` honored; a member without a `pyproject.toml` is skipped, not an error

Two deliberate divergences from real `uv`, both because mutate4py's job is *finding
Python files*, not validating a workspace:

- **`[tool.uv.workspace].exclude` is honored** (not required by the acceptance
  criteria — an intentional addition) and prunes **both** the member list **and**
  the workspace root's recursive walk. The two prune sites matter: excluding a
  member directory from the *list* but not the *walk* would silently readmit its
  files the moment the root's recursive collector reached them, since they
  physically sit under the root. Pruning is by `os.path.realpath` identity, checked
  during the walk, not by re-encoding the excluded path as a `--exclude`-style glob
  string — a directory literally named with a glob metacharacter would otherwise be
  able to falsely exclude an unrelated sibling.
- **A `members`-glob match with no `pyproject.toml` is skipped silently.** Real `uv`
  treats that as an error. mutate4py doesn't validate the workspace — a directory
  that happens to match a members glob but isn't (yet) a real package is exactly the
  kind of thing a mutation tool should walk past quietly, not block a run over.

## 5. Python floor raised to 3.11 for stdlib `tomllib`

`tomllib` is stdlib from 3.11; the project was `requires-python = ">=3.10"`.
Autodiscovery needs to parse `pyproject.toml`, and mutate4py's `dependencies = []`
(zero runtime deps, spec §1) is a stated design value, not an accident — adding
`tomli` as a conditional dependency to keep 3.10 would trade a real promise for a
version nobody was verifying anyway (no CI version matrix, `.python-version` pins
3.14). The project is pre-1.0 (0.1.1), so narrowing the floor now is cheap.

## Departure from ADR 0014's `[PORT]` posture

ADR 0014 pins F5's flag-matrix validation as a faithful port of upstream
`cli.go`'s `ValidateArgs`. That still holds, unchanged, for the flag matrix itself —
mutual exclusion, positive-int flags, missing-value checks all validate exactly as
before. What #22 adds is a **new phase with no upstream analogue at all**: *target
resolution*, which runs after flag validation and before dispatch, turning the
positional(s) into a concrete file list. Upstream has nothing to port here because
upstream's target is always "the one path the caller gave," full stop — there is no
`internal/cli/cli.go` code path for "zero or several targets" to diverge from. This
ADR is `[PY]` territory in the same sense ADR 0008 was for the coverage flags: the
shape is mutate4py's own, made to fit Python's ecosystem (uv workspaces) rather than
mutate4go's (a single Go module, one binary, one target per run).

**Considered and rejected:** a new `--workspace`/`--discover` flag for
autodiscovery (rejected — zero positionals is already an unambiguous, discoverable
trigger, and a flag would make the common case, `cd workspace-root && mutate4py`,
one keystroke longer for no disambiguation benefit); adding `tomli` as a
conditional dependency to keep the 3.10 floor (rejected — trades away the
zero-runtime-deps guarantee for a Python version the project never actually tested
against); erroring on a `members`-glob match with no `pyproject.toml`, matching real
`uv` (rejected — validating the workspace isn't mutate4py's job, and a false
positive there would block a run for a reason unrelated to mutation testing);
widening `_collect_py_files`'s signature to accept multiple roots directly
(rejected in #22 phase A already — the single-root signature is mapped over, kept
for the same reason a directory walk shouldn't also own union semantics).
