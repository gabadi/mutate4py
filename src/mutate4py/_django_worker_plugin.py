"""pytest plugin loaded per-Worker (`-p mutate4py._django_worker_plugin`) so
pytest-django gets the per-Worker test-database identity it otherwise only
gets from pytest-xdist (issue 05).

pytest-django derives its per-worker test-database suffix from
`config.workerinput["workerid"]`, an attribute only pytest-xdist populates.
mutate4py's Workers are not xdist Workers, so without this every Worker's
test database collides during migration. `_worker_server.py` sets
`MUTATE4PY_WORKER_ID` once per Worker and registers this plugin on every
dispatched pytest invocation; outside a Worker (serial runs) the env var is
unset and `pytest_configure` is a no-op.

A plain module-level hook, not a class, because it must load the same way
whether the mutant runs in-process (the forking executor, which inherits the
Worker's environment across fork()) or as a genuinely separate OS process
(the subprocess executor) — a live plugin object can't cross that boundary,
but `-p <module>` plus an inherited environment variable can.
"""

import os

__all__: list[str] = []


def pytest_configure(config) -> None:
    # Never overwrite a real xdist workerinput: a user routing `-n auto`
    # through --pytest-args for intra-Worker parallelism already has one,
    # and it must win over this synthetic identity.
    if hasattr(config, "workerinput"):
        return
    worker_id = os.environ.get("MUTATE4PY_WORKER_ID")
    if worker_id:
        config.workerinput = {"workerid": worker_id}
