"""Worker tree provisioning: the filesystem and uv mechanics behind one
Worker's isolated copy (ADR 0015). `_workers.py` owns the orchestration and
the failure taxonomy; this module only copies, provisions the venv, and links
the import root.
"""

import json
import os
import shutil
import subprocess
import sys

from mutate4py._worker_protocol import WorkerProcessError, check_worker_python, worker_python

_SKIP_ENTRIES = {
    ".git",
    "__pycache__",
    ".venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".mutate4py",
}


def _copy_tree(src_dir: str, dst_dir: str) -> None:
    """Copy src_dir to dst_dir, skipping _SKIP_ENTRIES at any level.
    A symlink is recreated, never followed (#79); see _symlink_target."""

    def copy(src: str, dst: str) -> None:
        os.makedirs(dst, exist_ok=True)
        for entry in os.scandir(src):
            if entry.name in _SKIP_ENTRIES:
                continue
            target = os.path.join(dst, entry.name)
            if entry.is_symlink():
                os.symlink(_symlink_target(entry.path, src_dir), target)
            elif entry.is_dir(follow_symlinks=False):
                copy(entry.path, target)
            else:
                shutil.copy2(entry.path, target)

    copy(src_dir, dst_dir)


def _symlink_target(link_path: str, root: str) -> str:
    """Where a Worker copy of link_path points: relative when the target is inside
    root, so it resolves into the Worker's own copy; absolute otherwise, because the
    Worker tree sits deeper than the original and a relative `../x` would miss."""
    target = os.path.realpath(link_path)
    real_root = os.path.realpath(root)
    if os.path.commonpath([target, real_root]) == real_root:
        return os.path.relpath(target, os.path.realpath(os.path.dirname(link_path)))
    return target


def _import_root_for(worker_root: str) -> str:
    """Sibling of the Worker tree (never inside it), so the copy cannot hold the link."""
    return os.path.abspath(worker_root) + "-import"


def _link_import_root(worker_root: str, package_dir: str) -> str:
    """Link the orchestrator's package as `mutate4py` in a symlink-only import root, and
    point the Worker venv at it through a `.pth` in its site-packages; return the root.

    A `.pth` is read after the venv's own entries, so the editable install's
    `_<name>.pth` wins: in a dogfood run the project's own mutate4py is imported, not the
    orchestrator's original. The import root supplies mutate4py only where the venv has
    none. It is deliberately not on PYTHONPATH, which would shadow the project's copy."""
    import_root = _import_root_for(worker_root)
    os.makedirs(import_root)
    os.symlink(package_dir, os.path.join(import_root, "mutate4py"))
    purelib = subprocess.run(
        [worker_python(worker_root), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    with open(os.path.join(purelib, "zzz_mutate4py_import_root.pth"), "w") as f:
        f.write(import_root + "\n")
    return import_root


_DISTRIBUTIONS_PROBE = (
    "import importlib.metadata as m, json; "
    "print(json.dumps(sorted({d.metadata['Name'].lower().replace('_', '-') for d in m.distributions()})))"
)


def check_worker_distributions(worker_root: str, required: frozenset[str]) -> None:
    """Refuse a Worker venv missing a distribution the project environment holds (ADR 0015).
    `uv sync` installs default groups only, so without this check the Baseline and the
    Mutants could run under different dependencies. An empty `required` skips the probe."""
    if not required:
        return
    try:
        probe = subprocess.run(
            [worker_python(worker_root), "-c", _DISTRIBUTIONS_PROBE],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as e:
        raise WorkerProcessError(f"worker venv at {worker_root!r} could not list its distributions: {e}") from e
    missing = required - set(json.loads(probe.stdout))
    if missing:
        raise WorkerProcessError(
            f"worker venv at {worker_root!r} lacks "
            f"{', '.join(sorted(missing)[:10])} installed in the project environment; "
            "Worker venvs are built with `uv sync` (default dependency groups, no extras): "
            "declare these in the project's dev dependency group"
        )


def _provision_venv(worker_root: str, required: frozenset[str]) -> None:
    """Run uv venv + uv sync in the Worker copy, pinned to the orchestrator's interpreter
    (as before M1), then check its interpreter's version and its distributions.

    Raises subprocess.CalledProcessError or OSError (uv missing) from the uv
    steps, and WorkerProcessError from the checks; `_workers` restates each as a
    WorkerFailureError.
    """
    for cmd in (["uv", "venv", "--python", sys.executable], ["uv", "sync", "--python", sys.executable]):
        subprocess.run(cmd, cwd=worker_root, capture_output=True, text=True, check=True)
    check_worker_python(worker_root)
    check_worker_distributions(worker_root, required)
