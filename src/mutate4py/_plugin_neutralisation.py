"""Neutralises the pytest plugins a Mutant run definitionally cannot use.

Why each plugin gets its own kill switch (`--no-cov`) and never `-p no:<name>`,
why every flag is gated on the plugin being importable, and why no other plugin
is touched: `docs/adr/0020-single-execution-model-and-plugin-neutralisation.md`.
Read it before adding, removing, or unguarding an entry in `_KNOWN_PLUGINS`.
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
