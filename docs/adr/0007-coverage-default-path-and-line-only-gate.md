# Line coverage only: branch coverage does not gate a Site

A Site is eligible when a test context of the Measurement reached its line.

## Considered Options

- **Gate on branch coverage.** It removes the boundary Mutants that the tool exists to find. `>` to `>=` on a line with partly covered branches is the most valuable Mutant of the file, and a branch gate never selects it.
