# Survivors fail the scored run and stay in the Manifest

A scored run with an unaccepted Survivor exits 3, the Manifest records each Survivor, and `# mutate4py: equivalent <reason>` on the mutated line accepts it.

## Considered Options

- **An opt-in `--fail-on-survivor`.** The default of a gate must gate.
- **A hand-edited `accepted` list as the source of truth.** It is dropped when the function changes, and the reason is far from the code.
- **Accept by category from `.agents/references/equivalent-mutants.md`.** That file is prose and records no verdict for each Site.
- **`--require-scored`.** Not necessary yet.
- **Merge the Sites of partial runs.** The score of a function that a run selected only in part cannot be known, so that function is skipped.
