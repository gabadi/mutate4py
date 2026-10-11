"""Plain module for the `uv run --with` overlay regression (ADR 0025).
The test imports it through pytest.ini's pythonpath, not a package."""


def is_adult(age):
    return age >= 18


def is_senior(age):
    return age >= 65
