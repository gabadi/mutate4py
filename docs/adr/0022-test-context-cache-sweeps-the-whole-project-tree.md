# Test-context cache: fingerprint the whole project tree, not the files a test looks like it uses

**Status:** accepted

The Test-context cache (issue #52) skips the ADR 0021 rebuild when it can prove
nothing that would change the db has changed. Proving that means fingerprinting
every input. The question this ADR settles is *which files are inputs*.

## The bug the narrow answers kept reproducing

A file the cache doesn't track is a file whose edit silently serves a stale db.
That is not a cache miss — it is ADR 0021's own failure mode, arriving by a
different route: `--test-contexts` reads a db that under-lists which tests cover
a line, a killing test never runs, and the mutant survives. Loud failures are
recoverable; this one isn't.

Three narrower rules were implemented and each was rejected on a concrete
counter-example:

1. **Node-id test files plus coverage-recorded source files.** Missed
   `conftest.py`, missed coverage's own config files, and missed every
   test-support module that a test imports but coverage's `source` restriction
   keeps out of the db.
2. **Add conftest.py and the coverage-config candidates.** Still missed plain
   test-support modules — `tests/factories.py`, `tests/helpers.py`.
3. **Every `.py` file beside the test file and beside each ancestor directory
   up to cwd.** Walks upward only, so it missed `tests/helpers/factories.py`
   imported by `tests/test_a.py` (a child of the test's own directory) and
   equally missed it when imported by `tests/unit/test_a.py` (a sibling
   subdirectory of an ancestor). It was also unbounded: a test file resolving
   outside cwd never reached the `== cwd` stop condition and climbed to the
   filesystem root.

The pattern is the point. Each rule was a guess at the import graph made from
directory shape, and each guess left a differently-shaped hole. A fourth guess
would have left a fifth.

## The decision

Sweep the whole project tree: every `.py` file under cwd, pruning
`__pycache__`, `venv`, `node_modules` and dot-directories (the same predicate
target resolution walks with, shared via `_py_tree.py`), unioned with each
node-id test file resolved by path. Fingerprint all of it.

This stops guessing which files matter and accepts that in a Python project
essentially every `.py` file either is source or supports a test. The cost is
one directory listing and one file read per project `.py` file — measured at
~59ms for this repo's 137 files — against a rebuild costing one coverage.py
session per test. Over-collecting is orders of magnitude cheaper than
under-collecting, and unlike under-collecting it fails in the safe direction.

Two bounds are deliberate, both at cwd:

- A node-id test file resolving outside cwd is tracked by path, but `.py` files
  merely sitting beside it are not.
- `os.walk` does not follow directory symlinks, so `tests/support ->
  /shared/support` is not swept either.

Outside the project root there is no bounded tree to sweep; following symlinks
would need cycle detection and would put arbitrary out-of-project directories
in the fingerprint. cwd is where tracking stops, and that is a stated limit
rather than an accident of the traversal.

## Rejected alternatives

**Parse the imports.** Resolving each test's real import graph would track
exactly the right files. It needs a working import resolver for arbitrary
project layouts, `sys.path` manipulation, plugins and dynamic imports — far
more machinery than a hash sweep, failing silently in the same direction as
the directory guesses whenever resolution comes up short.

**Track mtimes instead of hashing.** Cheaper, but a checkout, a rebase or a
`touch` invalidates for nothing, and clock skew or a preserved mtime can miss a
real edit. Hashing also keeps acceptance criterion 4's "reuses or parallels the
Manifest's existing hashing approach".

**Let one unreadable file discard the whole fingerprint.** The first
implementation returned `None` for a hash group if any single file in it was
unreadable, which discarded the cache entirely. One permission-denied file
anywhere in the tree then disabled caching permanently. Unreadable is now
recorded per file as `null`: still unreadable reads as unchanged, and becoming
readable invalidates.

**Narrow the staleness check to edits that provably change coverage.** Proving
an edit left coverage unchanged requires rebuilding to find out, which is the
thing being avoided. `is_cache_fresh` over-approximates staleness on purpose.
