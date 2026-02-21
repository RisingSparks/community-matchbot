"""Shared logging setup for CLI and runtime services."""

from __future__ import annotations

import logging
import warnings

from matchbot.settings import get_settings

_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s - %(message)s"


def configure_logging(verbose: bool | None = None) -> bool:
    """
    Configure root logging and warning capture.

    Returns the effective verbose mode.
    """
    if verbose is None:
        verbose = get_settings().verbose

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format=_LOG_FORMAT, force=True)
    logging.captureWarnings(True)

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
