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
