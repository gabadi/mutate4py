# Three test levels: unit, system, acceptance

A test is `unit` (in-process, the only level that the Measurement and coverage read) or `system` (real processes), and acceptance runs the Gherkin features.

## Considered Options

- **Two levels, unit and acceptance.** Acceptance drives full CLI runs and does not pin the internals of those runs: fork-server parity with the subprocess executor, hang recovery, the choice between swap and fresh-import mode, the Measurement internals, the stored tests digest, and the Django worker protocol. If those tests move into the unit set, real processes go into the Measurement.
