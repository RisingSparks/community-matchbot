"""Shared logging setup for CLI and runtime services."""

from __future__ import annotations

import logging
import warnings

from matchbot.settings import get_settings

_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s - %(message)s"
_APP_LOGGER = "matchbot"
_QUIET_LOGGERS = (
    "aiosqlite",
    "httpcore",
    "httpx",
    "openai",
)

_DISCORD_WARNING_FILTERS = (
    "parameter 'timeout' of type 'float' is deprecated",
)

_DISCORD_LOG_SUPPRESSED = (
    "PyNaCl is not installed",
)


class _DiscordWarningFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not any(msg in record.getMessage() for msg in _DISCORD_LOG_SUPPRESSED)

    @classmethod
    def install(cls) -> None:
        f = cls()
        logging.getLogger("discord").addFilter(f)


def configure_logging(verbose: bool | None = None) -> bool:
    """
    Configure root logging and warning capture.

    Returns the effective verbose mode.
    """
    if verbose is None:
        verbose = get_settings().verbose

    # Keep root at INFO so third-party DEBUG output stays quiet.
    logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT, force=True)
    logging.captureWarnings(True)

    app_logger = logging.getLogger(_APP_LOGGER)
    app_logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    for logger_name in _QUIET_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    # Suppress known noisy discord.py warnings.
    for msg in _DISCORD_WARNING_FILTERS:
        warnings.filterwarnings("ignore", message=msg)
    _DiscordWarningFilter.install()

    if verbose:
        # Ensure deprecations/runtime warnings are visible while debugging.
        warnings.simplefilter("default")

    return verbose


def log_exception(logger: logging.Logger, message: str, *args: object) -> None:
    """Log an exception with traceback in verbose mode, otherwise concise error."""
    if get_settings().verbose:
        logger.exception(message, *args)
    else:
        logger.error(message, *args)
