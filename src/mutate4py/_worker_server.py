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

import json
import logging
import os
import sys
from typing import TextIO

from mutate4py._executor import Executor
from mutate4py._executor_selection import _prepare_executor

__all__ = ["main"]

_DJANGO_WORKER_PLUGIN_ARGS = ["-p", "mutate4py._django_worker_plugin"]


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
    cwd, guarded_path, forking_flag = argv[0], argv[1], argv[2]
    worker_id = argv[3] if len(argv) > 3 and argv[3] else None
    if worker_id is not None:
        os.environ["MUTATE4PY_WORKER_ID"] = worker_id
    executor = _prepare_executor(requested=forking_flag == "1", cwd=cwd, guarded_path=guarded_path)
    sys.stdout.write(json.dumps({"ready": True}) + "\n")
    sys.stdout.flush()
    _serve(executor, sys.stdin, sys.stdout, worker_id=worker_id)


if __name__ == "__main__":
    main(sys.argv[1:])
