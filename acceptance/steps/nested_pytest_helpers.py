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

Unit tests: tests/test_nested_pytest_helpers.py.
"""

import os
from collections.abc import Mapping

AUTOLOAD_SWITCH = "PYTEST_DISABLE_PLUGIN_AUTOLOAD"
ADDOPTS = "PYTEST_ADDOPTS"
NESTED_PYTEST_PLUGINS = ("pytest_cov",)


def nested_pytest_env(base: Mapping[str, str] | None = None, *, autoload: bool = False) -> dict[str, str]:
    """A copy of `base` (default: os.environ) for a mutate4py run in a fixture project.

    With `autoload` False the nested pytest runs load no plugin but the ones named in
    NESTED_PYTEST_PLUGINS. With `autoload` True they load whatever their environment installs,
    as a user's run does: the switch and the plugin flags are removed even if `base` set them."""
    env = dict(os.environ if base is None else base)
    if autoload:
        env.pop(AUTOLOAD_SWITCH, None)
        env.pop(ADDOPTS, None)
        return env
    env[AUTOLOAD_SWITCH] = "1"
    flags = [f"-p {plugin}" for plugin in NESTED_PYTEST_PLUGINS]
    env[ADDOPTS] = " ".join([env[ADDOPTS], *flags]) if env.get(ADDOPTS) else " ".join(flags)
    return env
