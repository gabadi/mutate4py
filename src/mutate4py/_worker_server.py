"""Worker-process entry point for parallel dispatch (issue 04b): a small
JSON-lines request/response server over stdin/stdout.

Spawned once per Worker by `_worker_protocol.WorkerProcessExecutor` — never
imported directly by orchestrator code — and stays alive for the Worker's
whole run: it primes exactly one Executor at startup (the same capability
probe the single-Worker path uses, `_prepare_executor`), signals readiness,
then answers one `run(args, timeout)` request per line until stdin closes.
This replaces spawning a fresh subprocess for every Mutant with one
persistent, already-primed process per Worker.

Invoked as `python -m mutate4py._worker_server <cwd> <guarded_path>
<forking_requested 0|1> <worker_id>`, using the orchestrator's own
interpreter (`sys.executable`) so `mutate4py` is always importable here
regardless of what a tree-copied Worker root's own provisioned venv happens
to contain.

`worker_id` (empty string when this Worker has none) gives pytest-django the
per-Worker test-database identity it otherwise only gets from pytest-xdist
(issue 05): it is set once as `MUTATE4PY_WORKER_ID` in this process's own
environment — inherited by a forked child automatically, and by a spawned
subprocess the same way any environment variable is — and `-p
mutate4py._django_worker_plugin` is added to every dispatched pytest
invocation to read it back.
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
