"""Worker-process entry point for parallel dispatch: a JSON-lines
request/response server over stdin/stdout.

Spawned once per Worker by `_worker_protocol.WorkerProcessExecutor` — never
imported by orchestrator code — and stays alive for the Worker's whole run:
one primed Executor per Worker answering one `run()` request per line, not a
fresh subprocess per Mutant. Keep it that way; the priming cost is the whole
reason this process exists.

The spawn uses the orchestrator's own interpreter (`sys.executable`), so
`mutate4py` is importable here regardless of what a tree-copied Worker root's
own provisioned venv contains.

`MUTATE4PY_WORKER_ID` is set in this process's environment rather than passed
per request, because a forked child inherits it for free; see
`_django_worker_plugin` for what reads it back and why.
"""

import dataclasses
import json
import logging
import os
import sys
from typing import TextIO

from mutate4py._executor import Executor
from mutate4py._executor_selection import _prepare_executor

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


def _serve(executor: Executor, instream: TextIO, outstream: TextIO, *, worker_id: str | None) -> None:
    """Answer one run() request per non-empty line until instream closes."""
    for line in instream:
        line = line.strip()
        if not line:
            continue
        request = json.loads(line)
        args = request["args"]
        if worker_id is not None:
            args = [*args, *_DJANGO_WORKER_PLUGIN_ARGS]
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
    _serve(executor, sys.stdin, sys.stdout, worker_id=args.worker_id)


if __name__ == "__main__":
    main(sys.argv[1:])
