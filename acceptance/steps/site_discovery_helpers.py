"""Pure helpers for the site-discovery acceptance steps.

Unit tests: tests/test_site_discovery_helpers.py.
"""

_WARNING_PREFIX = "Warning:"


def warning_lines(stdout: str) -> list[str]:
    """The lines of a run's stdout that are over-threshold warnings, in print order."""
    return [line for line in stdout.splitlines() if line.startswith(_WARNING_PREFIX)]


def assert_warning_line(stdout: str, expected: str) -> None:
    """The run printed exactly the `expected` warning line, or no warning when `expected` is empty.

    `expected` is the feature's literal text: it is compared with the real output, never rebuilt here."""
    printed = warning_lines(stdout)
    wanted = [expected] if expected else []
    assert printed == wanted, f"expected warning lines {wanted!r}, the run printed {printed!r}:\n{stdout}"
