# F5 CLI validation mirrors upstream `internal/cli/cli.go`

**Status:** accepted
**Feature:** F5 (cli-surface) · **Spec:** §2 · **Ground truth:**
`unclebob/mutate4go` `internal/cli/cli.go` (`ValidateArgs`, `consumeValueOption`,
`parsePositiveInt`, `parseLines`)

F5 owns the §2 flag matrix: parse every flag, validate it, reject illegal
combinations with a usage error, and dispatch the accepted options. The exact
validation rules are a `[PORT]` of upstream `cli.go`, cross-checked against the spec
§2 mutual-exclusion list. This ADR pins the rules so they are not re-derived from
prose.

## Parse + validation rules (from `cli.go`)

- **`--help`** short-circuits before any validation: print the usage summary and
  exit 0, regardless of other (even invalid) args. (`cli.go:63–71`)
- **Value flags** (`--lines`, `--mutation-warning`, `--timeout-factor`,
  `--test-command`, `--max-workers`) consume the next arg; a missing value is a usage
  error (`Missing value for <flag>.`). (`cli.go:110–113`)
- **Positive-int flags** (`--mutation-warning`, `--timeout-factor`, `--max-workers`)
  reject non-integer and non-positive values: `n <= 0` or non-numeric → usage error.
  Upstream message: `invalid value for <flag>. Expected a positive integer`.
  (`parsePositiveInt`, `cli.go:198–204`)
- **`--lines`** parses a comma-separated list of **positive** integers; any
  non-positive or non-integer element → usage error. (`parseLines`, `cli.go:186–196`)
- **`--scan`** rejects if combined with `--update-manifest`, `--lines`,
  `--since-last-run`, `--mutate-all`, a non-default `--timeout-factor` or
  `--test-command`, or `--max-workers`. (`cli.go:87–90`)
- **`--update-manifest`** rejects the symmetric set (with `--scan`). (`cli.go:93–96`)
- **`--since-last-run` / `--mutate-all` / `--lines`** are **pairwise exclusive**, and
  each also rejects combining with `--scan`/`--update-manifest`.
  (`cli.go:101–108`, `145–147`)
- **`--max-workers`** is a positive int and joins **only** the
  scan/update-manifest exclusion (ADR 0013); it does **not** conflict with the
  selection flags — it may combine with `--lines`/`--since-last-run`/`--mutate-all`.
- **Unknown `--flag`** → usage error (`Unknown option: <flag>`). (`cli.go:121–123`)
- **Missing source file** (no positional, or the path does not exist) → usage error.
  (`cli.go:133–138`)
- **Defaults:** `--mutation-warning` 50, `--timeout-factor` 10,
  `--test-command` `pytest` ([PY], spec §2), `--max-workers` 0/unset = serial.

## `[PY]` divergences from upstream

- `--test-command` default is **`pytest`**, not `go test ./...` (spec §2 [PY]).
- The coverage flags (`--cov-cmd` / `--lcov` / `--reuse-coverage`) are **[PY]**
  additions (upstream has one Go coverprofile path); their pairwise exclusivity is
  ADR 0008. F5 wires them into the same fail-loud validation matrix.
- F5 specifies validation **outcomes** (usage error, non-zero exit, no run) as the
  observable contract. The exact parser implementation (argparse vs hand-rolled) and
  the exact exit code are the coder's to pin; the Gherkin parameterizes the message
  text and asserts non-zero exit, not a specific code.
