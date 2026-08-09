"""Package init: configures logging once, at import time, so every module's
logging.getLogger(__name__) call (a child of the "mutate4py" logger below) is
routed correctly regardless of entry point — the CLI, the installed
console-script, or a test importing a submodule directly without ever going
through __main__.main().
"""

import logging
import sys

_LOG_FORMAT = "%(message)s"


class _MaxLevelFilter(logging.Filter):
    """Caps a handler at max_level (inclusive) — Handler.setLevel only sets a floor."""

    def __init__(self, max_level: int) -> None:
        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.max_level


class _LiveStreamHandler(logging.StreamHandler):
    """Resolves sys.stdout/sys.stderr at emit time, not at construction time —
    matching print()'s own lookup behavior, so pytest's capsys (which swaps
    sys.stdout/sys.stderr for the duration of each test) captures logged
    output exactly as it captured the print() calls this replaces.
    """

    def __init__(self, stream_attr: str) -> None:
        logging.Handler.__init__(self)
        self._stream_attr = stream_attr

    @property
    def stream(self):
        return getattr(sys, self._stream_attr)

    @stream.setter
    def stream(self, value) -> None:
        pass


def _configure_logging() -> None:
    logger = logging.getLogger("mutate4py")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    stdout_handler = _LiveStreamHandler("stdout")
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.addFilter(_MaxLevelFilter(logging.INFO))
    stdout_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    logger.addHandler(stdout_handler)

    stderr_handler = _LiveStreamHandler("stderr")
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    logger.addHandler(stderr_handler)


_configure_logging()
