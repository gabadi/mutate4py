# A per-function tests digest decides whether a scored function is still proven

The `tests_digest` of a function hashes the test files that reach its covered Site lines, their conftests and the support files. A function whose Unit hash and digest did not change is skipped, and a run whose `tests_fingerprint` did not change skips its Measurement.

## Considered Options

- **One digest over the whole tests tree** (the `.harden-proof.json` of a consumer). Each test edit invalidates each proof, which is the problem of issue #88. This holds for `.py` test files. A non-Python file under a test folder is a support file.
- **A digest over each line in the span of the function.** The `def` and decorator lines make a test that only imports the module an input.
- **An upgrade branch that scores each 0.2.x entry again.** A clean entry has nothing to prove again, and its digest costs one read.
- **A Mutation Report from the stored totals on a skipped run.** The numbers would look like the score of this run, but this run scored nothing.
- **Skip for each target in a batch.** The batch shares one Measurement, so a partial skip still measures the files that it should skip.
- **Stop the fingerprint walk at the nearest `pyproject.toml`.** In a monorepo it can be below a conftest or a pytest config that pytest loads. Pytest skips a `pyproject.toml` with no pytest table when a real inifile is above it.
- **Find the files that a test opens.** The Measurement records imports, not file reads, so that set cannot be known without a trace of each `open`.
- **Walk only the directories of the test files for non-Python files.** A fixture directory next to the test directories (`tests/data` next to `tests/unit`) is then missed.
