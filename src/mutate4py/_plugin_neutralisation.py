"""Neutralises the pytest plugins a Mutant run definitionally cannot use.

Why each plugin gets its own kill switch (`--no-cov`) and never `-p no:<name>`,
why every flag is gated on the plugin being importable, and why no other plugin
is touched: `docs/adr/0020-single-execution-model-and-plugin-neutralisation.md`.
Read it before adding, removing, or unguarding an entry in `_KNOWN_PLUGINS`.
"""

import importlib.util
from collections.abc import Callable

__all__ = ["disabled_plugin_args", "neutralising_args"]

_KNOWN_PLUGINS: tuple[tuple[str, str], ...] = (
    ("pytest_cov", "--no-cov"),
    ("pytest_benchmark", "--benchmark-disable"),
)


def neutralising_args(is_importable: Callable[[str], object | None] = importlib.util.find_spec) -> list[str]:
    """One disable flag per known plugin that is actually importable here."""
    return [flag for module_name, flag in _KNOWN_PLUGINS if is_importable(module_name) is not None]


def disabled_plugin_args(pytest_args: list[str]) -> list[str]:
    """The run's own plugin blocks (`-p no:<name>` or `-pno:<name>`), each as `-p no:<name>`.

    The forking executor primes with these, so a plugin the run disables is
    never loaded into the process every Mutant's child forks from.
    """
    blocks = []
    tokens = iter(pytest_args)
    for token in tokens:
        value = next(tokens, "") if token == "-p" else token[2:] if token.startswith("-p") else ""
        if value.startswith("no:"):
            blocks += ["-p", value]
    return blocks
