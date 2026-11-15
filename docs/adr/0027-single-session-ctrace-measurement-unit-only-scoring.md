# One single-session ctrace Measurement per run; code mutation scores with unit tests only

A scored run gets its Coverage gate, its Baseline and its Test map from one pytest session under the `ctrace` core of coverage.py.

## Considered Options

- **The `sysmon` core.** On the 2,087 function-body lines of this repo, its line map agrees with a per-test reference on 122 lines, against 1,982 for `ctrace`, because it drops each context after the first that reaches a line. A run whose core is `sysmon` exits 2.
- **Shard the Measurement.** It is not necessary when only unit tests score, and it adds empty-shard and collection-mismatch failures.
