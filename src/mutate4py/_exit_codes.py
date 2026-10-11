"""Process exit codes and the batch severity order (ADR 0018, ADR 0026)."""

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_SURVIVORS = 3

_SEVERITY_ORDER = (EXIT_USAGE, EXIT_FAILURE, EXIT_SURVIVORS, EXIT_OK)  # most severe first


def _rank(code: int) -> int:
    """Lower rank is more severe; a code outside the table ranks above EXIT_USAGE."""
    if code in _SEVERITY_ORDER:
        return _SEVERITY_ORDER.index(code)
    return -1


def worse_exit_code(a: int, b: int) -> int:
    """The more severe of two exit codes: 2 > 1 > 3 > 0. A code outside the table ranks above 2; on a tie, a."""
    return b if _rank(b) < _rank(a) else a


def scored_run_exit_code(unaccepted_survivors: int, *, allow_survivors: bool) -> int:
    """3 when unaccepted_survivors > 0 and survivors are not allowed, else 0."""
    if unaccepted_survivors > 0 and not allow_survivors:
        return EXIT_SURVIVORS
    return EXIT_OK
