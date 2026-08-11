"""Staleness cache for --build-test-contexts, mirroring the Manifest's
sha256-fingerprint approach (see _manifest.py) instead of inventing a second
hashing / JSON-serialization mechanism.

Fingerprints every .py file under cwd — test files, conftest.py, helpers and
factories, and source alike — plus every test file a collected node ID names,
any present coverage-config file, and every source file the just-built
coverage db recorded, so a later run can tell whether any of these changed
since the last build without re-running any per-test coverage session.
"""

import hashlib
import os
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from mutate4py._py_tree import walkable_dirs
from mutate4py._sidecar_io import read_json_sidecar, write_json_sidecar

__all__ = [
    "build_cache",
    "cache_path",
    "discard_cache",
    "is_cache_fresh",
    "read_cache",
    "should_skip_rebuild",
    "write_cache",
]

_VERSION = 2

# coverage.py reads its config from whichever of these exists (in this
# priority order); a config edit (e.g. flipping `branch = true`) changes what
# a rebuild would record without touching any covered source file, so it must
# invalidate the cache the same as a source-file edit (issue #52 review
# finding 1).
_COVERAGE_CONFIG_CANDIDATES = (".coveragerc", "pyproject.toml", "setup.cfg", "tox.ini")


def cache_path(output_db_path: str) -> str:
    """Sidecar cache path for a test-context db: <output_db_path>.test-context-cache.json."""
    return output_db_path + ".test-context-cache.json"


def _node_id_file(node_id: str) -> str:
    return node_id.split("::", 1)[0]


def _resolve(path: str, *, cwd: str) -> str:
    return os.path.normpath(path if os.path.isabs(path) else os.path.join(cwd, path))


def _project_py_files(cwd: str) -> set[str]:
    """Every .py file under cwd, pruned subtrees aside.

    Sweeping the whole project tree, rather than trying to work out which
    files a given test imports, is deliberate. Every narrower rule tried here
    left some shape of test-support module invisible — first conftest.py-only
    (missed helpers and factories), then ".py files beside the test and up its
    ancestor directories" (missed a helper in a subdirectory, and a helper in
    a sibling subdirectory of an ancestor). A file the cache cannot see is a
    file whose edit silently serves a stale db, which is ADR 0021's failure
    mode. The sweep costs one directory listing and one file read per project
    .py file; the rebuild it guards costs one coverage.py session per test, so
    over-collecting here is orders of magnitude cheaper than under-collecting.

    os.walk swallows unreadable directories rather than raising, so a
    permission-denied subtree narrows the sweep instead of failing the build.
    It also does not follow directory symlinks, so a symlink pointing out of
    the tree (tests/support -> /shared/support) is not swept — same boundary
    as _tracked_py_paths', reached from inside the tree instead of outside it.
    Following them would need cycle detection and would put arbitrary
    out-of-project directories in the fingerprint; the tree stops at cwd.
    """
    found: set[str] = set()
    for root, dirs, files in os.walk(cwd):
        dirs[:] = walkable_dirs(dirs)
        found |= {os.path.normpath(os.path.join(root, name)) for name in files if name.endswith(".py")}
    return found


def _tracked_py_paths(node_ids: Iterable[str], *, cwd: str) -> set[str]:
    """Every .py file whose content could change what a rebuild records.

    That is the project tree (see _project_py_files) plus each node-id test
    file, which is normally already inside the tree but may resolve outside it
    when pytest is pointed at tests elsewhere. Such a test file is tracked by
    path; .py files merely sitting beside it are not — outside cwd there is no
    bounded tree to sweep, so the project root is where tracking stops.
    """
    return _project_py_files(cwd) | {_resolve(_node_id_file(n), cwd=cwd) for n in node_ids}


def _coverage_config_paths(*, cwd: str) -> set[str]:
    """Every coverage.py config-file candidate present at cwd (see _COVERAGE_CONFIG_CANDIDATES)."""
    return {name for name in _COVERAGE_CONFIG_CANDIDATES if os.path.isfile(os.path.join(cwd, name))}


def _hash_file(path: str, *, cwd: str) -> str | None:
    """sha256 of path's raw bytes, or None if the file can't be read — never
    raises. Hashes bytes directly (not via source_sha256's str-then-encode
    path) so a non-UTF-8 source file can't crash this — see issue #52 review
    finding 2."""
    try:
        with open(_resolve(path, cwd=cwd), "rb") as f:
            data = f.read()
    except OSError:
        return None
    return hashlib.sha256(data).hexdigest()


def _hash_files(paths: Iterable[str], *, cwd: str) -> dict[str, str | None]:
    """Hash every distinct path, recording None for any that can't be read.

    An unreadable file is a fact about the tree worth remembering, not a
    reason to abandon the whole fingerprint. Recording None keeps the rest of
    the group usable, and still invalidates the cache if that file later
    becomes readable — where failing the whole group would instead disable
    caching for good, turning one permission-denied file into a permanent
    full rebuild.
    """
    return {path: _hash_file(path, cwd=cwd) for path in sorted(set(paths))}


def _covered_source_paths(db_path: str) -> list[str]:
    """Every source path coverage.py recorded in the just-built db's `file` table."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT path FROM file")
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def _current_hashes(node_ids: Iterable[str], *, cwd: str) -> tuple[dict[str, str | None], dict[str, str | None]]:
    """The project-.py and coverage-config hash groups as they stand right now.

    One function so that writing a cache and checking one compute these the
    same way by construction: if the two ever drifted apart, every run would
    see a difference that isn't there and rebuild forever, or — worse — miss
    one that is.
    """
    return (
        _hash_files(_tracked_py_paths(node_ids, cwd=cwd), cwd=cwd),
        _hash_files(_coverage_config_paths(cwd=cwd), cwd=cwd),
    )


def build_cache(node_ids: list[str], *, cwd: str, output_db_path: str) -> dict:
    """Fingerprint a just-completed build: node IDs, project .py file hashes,
    coverage-config hashes, and covered source file hashes.
    """
    py_files, config_files = _current_hashes(node_ids, cwd=cwd)
    return {
        "version": _VERSION,
        "node_ids": sorted(set(node_ids)),
        "py_files": py_files,
        "config_files": config_files,
        "source_files": _hash_files(_covered_source_paths(output_db_path), cwd=cwd),
    }


def _matches_build_identity(cache: dict, node_ids: Iterable[str]) -> bool:
    """Whether cache even describes the build being asked about: written by
    this _VERSION, and for this exact set of node IDs. The two checks that
    need no file read, so they come first."""
    return cache.get("version") == _VERSION and sorted(set(node_ids)) == cache.get("node_ids")


def is_cache_fresh(cache: dict, *, node_ids: list[str], cwd: str) -> bool:
    """True iff the current node IDs and every hashed file's content still match cache.

    Deliberately over-approximates staleness: ANY change to a tracked file
    invalidates the cache, whether or not that specific edit actually changes
    which tests cover which Selected sites. Proving the narrower claim — that
    an edit left coverage unchanged — would require rebuilding to find out,
    which defeats the point of caching. A stale test-context db silently
    narrows Mutants onto tests that no longer cover them (worse than an
    unneeded rebuild), so this always rebuilds when it can't prove nothing
    changed. Don't narrow this check.

    A cache written by any other _VERSION is stale by definition: what the
    fields mean is version-specific, so a future version that happens to reuse
    today's key names must not be read as if it were this one.
    """
    if not _matches_build_identity(cache, node_ids):
        return False
    py_files, config_files = _current_hashes(node_ids, cwd=cwd)
    if py_files != cache.get("py_files"):
        return False
    if config_files != cache.get("config_files"):
        return False
    for path, expected in cache.get("source_files", {}).items():
        if _hash_file(path, cwd=cwd) != expected:
            return False
    return True


def should_skip_rebuild(*, output_db_path: str, node_ids: list[str], cwd: str) -> bool:
    """True iff output_db_path already exists and its cache proves nothing
    that would change it — no project .py file, coverage-config file, or
    previously covered source file — has changed since it was built."""
    if not os.path.isfile(output_db_path):
        return False
    cache, ok = read_cache(output_db_path)
    return ok and is_cache_fresh(cache, node_ids=node_ids, cwd=cwd)


def read_cache(output_db_path: str) -> tuple[dict | None, bool]:
    """Read output_db_path's sidecar cache. Missing file or parse failure => (None, False)."""
    return read_json_sidecar(cache_path(output_db_path))


def write_cache(output_db_path: str, cache: dict) -> None:
    """Write output_db_path's sidecar cache."""
    write_json_sidecar(cache_path(output_db_path), cache)


def discard_cache(output_db_path: str) -> None:
    """Remove output_db_path's sidecar cache, if any. No-op if already absent.

    Called before a rebuild starts, so that a build which crashes partway
    through leaves no cache describing the db it was overwriting — a later run
    must not trust a fingerprint taken of a db that no longer exists in that
    form (issue #52 review finding 3).
    """
    Path(cache_path(output_db_path)).unlink(missing_ok=True)
