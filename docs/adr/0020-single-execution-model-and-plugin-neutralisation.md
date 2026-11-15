# Plugins are turned off by their own kill switch, not by `-p no:`

The Measurement and each Mutant run give `--no-cov` to pytest-cov and `--benchmark-disable` to pytest-benchmark, unless the child pytest provably does not load that plugin.

## Considered Options

- **`-p no:<name>`.** The plugin then does not register its options, so the `addopts = "--cov=..."` of a project becomes a pytest usage error.
- **Turn off other plugins.** Some plugins are necessary for correct results, and this layer cannot tell which. The Per-Mutant overhead hint names `-p no:<plugin>` in `--pytest-args` for a manual audit.
- **Catch exit 4 and run again without the switch.** The Baseline runs two times, and a real usage error is hidden.
- **Give `-p pytest_cov` when plugin autoload is off.** It loads a plugin that the user chose not to load, and registers it under a second name when the user names `pytest_cov.plugin`.
