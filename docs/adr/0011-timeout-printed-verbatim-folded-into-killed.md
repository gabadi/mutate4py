# `timeout` is visible per Mutant and folded into `Killed` in the report

A Mutant that times out prints `timeout` on its progress line, and the Mutation Report counts it in `Killed`.

## Considered Options

- **A `Timeout:` line in the Mutation Report.** A Mutant that did not end in its timeout did not survive, so it is a kill.
- **Print `killed` on the progress line of a timed-out Mutant.** A hung or slow Mutant then looks the same as a Mutant that a test killed.
- **One colon style for the progress line and the `Survivors:` lines.** The progress line puts a colon before the FunctionID (`a > b -> a >= b: func/calc`) and a `Survivors:` line does not (`a > b -> a >= b func/calc`), as upstream does (`runner.go:346` against `:622` and `:644`).
