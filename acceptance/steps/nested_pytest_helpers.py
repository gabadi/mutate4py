"""The environment acceptance gives the pytest runs that mutate4py launches in a fixture project.

pytest loads every plugin it finds through entry points before the first test, which costs
about half of a nested run and a Run starts many of them (the Measurement, each Mutant,
each Survivor confirmation). So acceptance turns autoload off and names the plugins a
fixture project needs, as `-p` flags in PYTEST_ADDOPTS:

- pytest_cov: mutate4py appends `--no-cov` to every nested run whenever pytest_cov is
  importable in its own interpreter (src/mutate4py/_plugin_neutralisation.py). The flag is
  only recognised once the plugin is loaded, so the plugin is named here. A Worker venv
  must then have pytest-cov too (parallel_workers_steps.py declares it in the fixture).

The fixture projects import nothing else: no hypothesis, no pytest-django, no xdist.
Exactly one scenario keeps autoload on (`autoload=True`), so the default user path stays
covered: parallel-workers-15, in parallel_workers_steps.py.

tests/conftest.py uses the same helper for the nested runs a system test launches, so there is one spelling of
the flags: the entry-point name (`-p pytest_cov`, never the module path `pytest_cov.plugin`). Two spellings
of one plugin make pytest die with "Plugin already registered under a different name". A flag the caller's
own PYTEST_ADDOPTS already carries is not added again, whichever of the two spellings it uses. The tests
import this module already (tach layers `src` only, so nothing forbids it).

Unit tests: tests/test_nested_pytest_helpers.py.
"""

import os
import shlex
from collections.abc import Mapping

AUTOLOAD_SWITCH = "PYTEST_DISABLE_PLUGIN_AUTOLOAD"
ADDOPTS = "PYTEST_ADDOPTS"
NESTED_PYTEST_PLUGINS = ("pytest_cov",)


def addopts_names_plugin(addopts: str, plugin: str) -> bool:
    """Whether `addopts` already loads `plugin` with `-p`, by its entry-point name or as a module path
    inside it (`pytest_cov.plugin`): adding the flag again would register the plugin twice."""
    tokens = shlex.split(addopts)
    named = [tokens[i + 1] for i, token in enumerate(tokens[:-1]) if token == "-p"]
    named += [token[2:] for token in tokens if token.startswith("-p") and token != "-p"]
    return any(name == plugin or name.startswith(plugin + ".") for name in named)


def nested_pytest_env(base: Mapping[str, str] | None = None, *, autoload: bool = False) -> dict[str, str]:
    """A copy of `base` (default: os.environ) for a mutate4py run in a fixture project.

    With `autoload` False the nested pytest runs load no plugin but the ones named in
    NESTED_PYTEST_PLUGINS, which are added to the caller's own PYTEST_ADDOPTS unless it names them
    already. With `autoload` True they load whatever their environment installs, as a user's run
    does: the switch is removed even if `base` set it, and the caller's PYTEST_ADDOPTS is kept."""
    env = dict(os.environ if base is None else base)
    if autoload:
        env.pop(AUTOLOAD_SWITCH, None)
        return env
    env[AUTOLOAD_SWITCH] = "1"
    addopts = env.get(ADDOPTS, "")
    flags = [f"-p {plugin}" for plugin in NESTED_PYTEST_PLUGINS if not addopts_names_plugin(addopts, plugin)]
    env[ADDOPTS] = " ".join(part for part in (addopts, *flags) if part)
    return env
