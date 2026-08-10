"""Neutralises the pytest plugins a Mutant run definitionally cannot use.

Coverage instrumentation is pure cost on a Mutant run: the run already holds
its own coverage (acquired once, up front, from `--lcov`/`--cov-cmd`), and
per-Mutant coverage from pytest-cov is never consumed. Benchmark timing is
unreliable under mutation testing — already a stated caution — and adds real
wall-clock cost to every invocation regardless. Both are disabled with the
plugin's own kill switch (`--no-cov`, `--benchmark-disable`) rather than
blocking the plugin outright (`-p no:<name>`): blocking prevents the plugin
from registering its options at all, which turns a project's own
`addopts = "--cov=..."` into "unrecognized arguments" — the kill switch is
built for exactly this override and leaves the option registered.

Both flags are pytest usage errors when their plugin is not installed, so
each is added only when the plugin is actually importable in this
interpreter — the same interpreter Mutant runs execute under (see
`_runner.run_baseline`).

Unknown plugins are never touched: some are load-bearing for correctness,
and this module only knows about the two above.
"""

import importlib.util
from collections.abc import Callable

__all__ = ["neutralising_args"]

_KNOWN_PLUGINS: tuple[tuple[str, str], ...] = (
    ("pytest_cov", "--no-cov"),
    ("pytest_benchmark", "--benchmark-disable"),
)


def neutralising_args(is_importable: Callable[[str], object | None] = importlib.util.find_spec) -> list[str]:
    """One disable flag per known plugin that is actually importable here."""
    return [flag for module_name, flag in _KNOWN_PLUGINS if is_importable(module_name) is not None]
