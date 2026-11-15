"""Neutralises the pytest plugins a Mutant run definitionally cannot use.

Why each plugin gets its own kill switch (`--no-cov`) and never `-p no:<name>`,
why every flag is gated on the plugin being importable (and `--no-cov` also on the
child loading pytest-cov), and why no other plugin is touched: `docs/adr/0020-single-execution-model-and-plugin-neutralisation.md`.
Read it before adding, removing, or unguarding an entry in `_KNOWN_PLUGINS`.
"""

import importlib.util
import os
import shlex
from collections.abc import Callable, Iterable, Mapping, Sequence

__all__ = ["disabled_plugin_args", "neutralising_args"]

_KNOWN_PLUGINS: tuple[tuple[str, str], ...] = (
    ("pytest_cov", "--no-cov"),
    ("pytest_benchmark", "--benchmark-disable"),
)

_AUTOLOAD_SWITCH = "PYTEST_DISABLE_PLUGIN_AUTOLOAD"
_ADDOPTS = "PYTEST_ADDOPTS"
_NEEDS_LOADING = "pytest_cov"


def neutralising_args(
    pytest_args: Sequence[str] = (),
    is_importable: Callable[[str], object | None] = importlib.util.find_spec,
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    """One disable flag per known plugin that is importable here.

    `--no-cov` also needs pytest-cov to be loaded by the pytest these args reach, or
    pytest exits 4 with "unrecognized arguments" (ADR 0020, amended): it is added
    only when autoload is on or `-p pytest_cov` is named in `pytest_args` or in PYTEST_ADDOPTS.
    """
    env = os.environ if environ is None else environ
    loads_cov = _loads_pytest_cov(pytest_args, env)
    return [
        flag
        for module_name, flag in _KNOWN_PLUGINS
        if is_importable(module_name) is not None and (loads_cov or module_name != _NEEDS_LOADING)
    ]


def _loads_pytest_cov(pytest_args: Sequence[str], env: Mapping[str, str]) -> bool:
    """Whether a pytest started with `pytest_args` in `env` loads pytest-cov."""
    if not env.get(_AUTOLOAD_SWITCH):
        return True
    try:
        addopts = shlex.split(env.get(_ADDOPTS, ""))
    except ValueError:
        addopts = []
    names = [*_plugin_names(pytest_args), *_plugin_names(addopts)]
    return any(name == _NEEDS_LOADING or name.startswith(_NEEDS_LOADING + ".") for name in names)


def _plugin_names(tokens: Iterable[str]) -> list[str]:
    """The value of every `-p <name>` and `-p<name>` in `tokens`."""
    names = []
    iterator = iter(tokens)
    for token in iterator:
        if token == "-p":
            names.append(next(iterator, ""))
        elif token.startswith("-p"):
            names.append(token[2:])
    return names


def disabled_plugin_args(pytest_args: list[str]) -> list[str]:
    """The run's own plugin blocks (`-p no:<name>` or `-pno:<name>`), each as `-p no:<name>`.

    The forking executor primes with these, so a plugin the run disables is
    never loaded into the process every Mutant's child forks from.
    """
    return [arg for name in _plugin_names(pytest_args) if name.startswith("no:") for arg in ("-p", name)]
