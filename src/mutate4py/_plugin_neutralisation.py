"""Neutralises the pytest plugins a Mutant run definitionally cannot use.

Why each plugin gets its own kill switch (`--no-cov`) and never `-p no:<name>`, why every flag is gated
on the plugin being importable, when the switch is dropped because the child pytest will not load the
plugin (and why the default is to keep it), and why no other plugin is touched:
`docs/adr/0020-single-execution-model-and-plugin-neutralisation.md`.
Read it before adding, removing, or unguarding an entry in `_KNOWN_PLUGINS`.
"""

import importlib.util
import os
import shlex
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import cached_property

from mutate4py._pytest_inifile import config_addopts, conftest_bounds
from mutate4py._pytest_session import pytest_start, run_conftests

__all__ = ["disabled_plugin_args", "neutralising_args"]


@dataclass(frozen=True)
class _Plugin:
    """A plugin with a kill switch.

    `module` is what must be importable here. `entry_point` is the name pytest registers it under, which
    `-p no:<entry_point>` blocks. `names` are the `-p` values, `PYTEST_PLUGINS` entries and conftest words
    that load it: each name, or a module path beneath it.
    """

    module: str
    flag: str
    entry_point: str
    names: tuple[str, ...]


_KNOWN_PLUGINS: tuple[_Plugin, ...] = (
    _Plugin("pytest_cov", "--no-cov", "pytest_cov", ("pytest_cov",)),
    _Plugin("pytest_benchmark", "--benchmark-disable", "benchmark", ("benchmark", "pytest_benchmark")),
)

_AUTOLOAD_SWITCH = "PYTEST_DISABLE_PLUGIN_AUTOLOAD"
_AUTOLOAD_OPTION = "--disable-plugin-autoload"
_ADDOPTS = "PYTEST_ADDOPTS"
_PLUGINS = "PYTEST_PLUGINS"
_BLOCK = "no:"


def neutralising_args(
    pytest_args: Sequence[str] = (),
    is_importable: Callable[[str], object | None] = importlib.util.find_spec,
    environ: Mapping[str, str] | None = None,
    cwd: str | None = None,
) -> list[str]:
    """One disable flag per known plugin that is importable here and that the child pytest may load.

    A flag is a pytest usage error (exit 4, "unrecognized arguments") in a pytest that does not load its
    plugin, and a plugin that is loaded but not told to stand down corrupts the Measurement: pytest-cov's
    Coverage pauses the Measurement's collector, so every Mutant scores Uncovered with exit 0. The second
    failure is silent, the first is loud, so the rule is: when unsure, keep the switch (ADR 0020, amended).
    A switch is dropped only when `_Session.loads` proves the child pytest, started in `cwd` with
    `pytest_args` and `environ`, does not load the plugin.
    """
    env = os.environ if environ is None else environ
    session = _Session(list(pytest_args), env, os.getcwd() if cwd is None else cwd)
    return [
        plugin.flag for plugin in _KNOWN_PLUGINS if is_importable(plugin.module) is not None and session.loads(plugin)
    ]


def _names(plugin: _Plugin, value: str) -> bool:
    """Whether a `-p` or `PYTEST_PLUGINS` value loads `plugin`: one of its names, or a module path beneath it."""
    return any(value == name or value.startswith(name + ".") for name in plugin.names)


class _Session:
    """What the pytest a run starts will load, read from the places that configure it.

    The places: the session args, `PYTEST_ADDOPTS`, the `addopts` of the inifile (found the way the tests
    digest finds it), `PYTEST_PLUGINS`, and the conftests the run loads. A source that does not parse (an
    unbalanced quote) leaves the answer unknown, and unknown means loaded.
    """

    def __init__(self, args: list[str], env: Mapping[str, str], cwd: str) -> None:
        self._args = args
        self._env = env
        self._cwd = cwd

    @cached_property
    def _starts(self) -> list[str]:
        """Where pytest's inifile search may begin, as the tests digest takes them."""
        return [self._cwd, pytest_start(self._cwd, self._args)]

    @cached_property
    def _env_and_ini(self) -> tuple[list[str], list[list[str]]] | None:
        """The `PYTEST_ADDOPTS` tokens and the token list of each inifile `addopts` that may be in effect;
        None when one of them does not parse."""
        try:
            env_tokens = shlex.split(self._env.get(_ADDOPTS, ""))
            return env_tokens, [shlex.split(a) for a in config_addopts(self._cwd, self._args, self._starts)]
        except ValueError:
            return None

    @cached_property
    def _autoload(self) -> bool:
        """Whether pytest autoloads plugins. Off needs the environment switch set non-empty, or the option in
        the args, in `PYTEST_ADDOPTS`, or in every inifile `addopts` that may be the one in effect."""
        env_tokens, ini = self._env_and_ini or ([], [])
        switched_off = bool(self._env.get(_AUTOLOAD_SWITCH)) or _AUTOLOAD_OPTION in (*self._args, *env_tokens)
        return not (switched_off or (ini and all(_AUTOLOAD_OPTION in tokens for tokens in ini)))

    @cached_property
    def _plugin_values(self) -> list[str]:
        """Every value of a `-p` in the args and the addopts, and every `PYTEST_PLUGINS` entry."""
        env_tokens, ini = self._env_and_ini or ([], [])
        values = [value for tokens in (self._args, env_tokens, *ini) for value in _plugin_names(tokens)]
        return [*values, *(entry.strip() for entry in self._env.get(_PLUGINS, "").split(","))]

    def _conftests_name(self, plugin: _Plugin) -> bool:
        """Whether any conftest the run loads contains one of the plugin's names as plain text."""
        bounds = conftest_bounds(self._cwd, self._args, self._starts)
        for path in run_conftests(self._cwd, self._args, bounds):
            try:
                with open(path, encoding="utf-8", errors="replace") as handle:
                    text = handle.read()
            except OSError:
                return True
            if any(name in text for name in plugin.names):
                return True
        return False

    def loads(self, plugin: _Plugin) -> bool:
        """Whether the child pytest may load `plugin`: false only when it provably does not.

        It loads when a source names it (whatever else is set), or autoload is on and nothing blocks it with
        `-p no:<entry point>`. Failing both, only a conftest naming it can still load it.
        """
        if self._env_and_ini is None or any(_names(plugin, value) for value in self._plugin_values):
            return True
        blocked = _BLOCK + plugin.entry_point in self._plugin_values
        return (self._autoload and not blocked) or self._conftests_name(plugin)


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
