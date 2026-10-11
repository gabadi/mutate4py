"""Worker-process entry point for parallel dispatch: a JSON-lines
request/response server over stdin/stdout.

Spawned once per Worker by `_worker_protocol.WorkerProcessExecutor` — never
imported by orchestrator code — and stays alive for the Worker's whole run:
one primed Executor per Worker answering one `run()` request per line, not a
fresh subprocess per Mutant. Keep it that way; the priming cost is the whole
reason this process exists.

The spawn runs under the Worker's own provisioned interpreter
(`<worker_root>/.venv/bin/python`), so the pytest this process drives, and the
plugin kill switches computed here, are the Worker venv's. `mutate4py` itself
is reached through a symlink-only import root on PYTHONPATH, so the
orchestrator's site-packages never leak into the Worker.

`MUTATE4PY_WORKER_ID` is set in this process's environment rather than passed
per request, because a forked child inherits it for free; see
`_django_worker_plugin` for what reads it back and why.
"""

import dataclasses
import json
import logging
import os
import sys
from collections.abc import Sequence
from typing import TextIO

from mutate4py._executor import Executor
from mutate4py._executor_selection import _prepare_executor
from mutate4py._plugin_neutralisation import neutralising_args

__all__ = ["WorkerServerArgs", "main", "parse_worker_argv", "worker_environ_updates"]

_DJANGO_WORKER_PLUGIN_ARGS = ["-p", "mutate4py._django_worker_plugin"]


@dataclasses.dataclass(frozen=True)
class WorkerServerArgs:
    """One Worker's startup parameters, as they crossed the process boundary."""

    cwd: str
    guarded_path: str
    forking_requested: bool
    worker_id: str | None


def parse_worker_argv(argv: list[str]) -> WorkerServerArgs:
    """Read back what `_worker_protocol.worker_server_argv` encoded.

    The worker_id slot is optional and may be present but empty (that is how
    the encoder spells "this Worker has no id"); both spellings decode to None.
    """
    return WorkerServerArgs(
        cwd=argv[0],
        guarded_path=argv[1],
        forking_requested=argv[2] == "1",
        worker_id=argv[3] if len(argv) > 3 and argv[3] else None,
    )


def worker_environ_updates(worker_id: str | None) -> dict[str, str]:
    """The environment entries this Worker's forked children must inherit;
    empty for a Worker with no id. See the module docstring for why this
    travels in the environment rather than per request."""
    if worker_id is None:
        return {}
    return {"MUTATE4PY_WORKER_ID": worker_id}


def _worker_plugin_args(worker_id: str | None) -> list[str]:
    """The plugin flags every dispatch from this Worker carries, computed by
    this process's own interpreter, which runs the pytest they apply to: the
    kill switches for plugins it can import, then the Django worker plugin
    (only for a Worker with an id: its plugin reads the id from the environment)."""
    return [*neutralising_args(), *(_DJANGO_WORKER_PLUGIN_ARGS if worker_id is not None else [])]


def _serve(executor: Executor, instream: TextIO, outstream: TextIO, *, plugin_args: Sequence[str]) -> None:
    """Answer one run() request per non-empty line until instream closes."""
    for line in instream:
        line = line.strip()
        if not line:
            continue
        request = json.loads(line)
        args = [*request["args"], *plugin_args]
        status = executor.run(args, request["timeout"])
        outstream.write(json.dumps({"status": status}) + "\n")
        outstream.flush()


def main(argv: list[str]) -> None:
    # mutate4py's package logger writes INFO records live to stdout (for CLI
    # progress) — a Worker subprocess's stdout is this JSON-lines protocol
    # instead, so any INFO log during executor selection (e.g. the
    # forking-unavailable fallback note) would corrupt framing exactly like
    # the unflushed-pytest-output bug already fixed for this protocol.
    logging.getLogger("mutate4py").setLevel(logging.WARNING)
    args = parse_worker_argv(argv)
    os.environ.update(worker_environ_updates(args.worker_id))
    executor = _prepare_executor(requested=args.forking_requested, cwd=args.cwd, guarded_path=args.guarded_path)
    sys.stdout.write(json.dumps({"ready": True}) + "\n")
    sys.stdout.flush()
    _serve(executor, sys.stdin, sys.stdout, plugin_args=_worker_plugin_args(args.worker_id))


if __name__ == "__main__":
    main(sys.argv[1:])
