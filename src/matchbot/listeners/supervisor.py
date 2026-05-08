"""Helpers for supervising long-running listener tasks."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from matchbot.log_config import log_exception

logger = logging.getLogger(__name__)


async def run_forever(
    name: str,
    starter: Callable[[], Awaitable[None]],
    *,
    retry_delay_seconds: float = 60.0,
) -> None:
    """Keep a listener alive without letting failures take down the process."""
    while True:
        try:
            await starter()
            logger.warning(
                "%s exited cleanly; restarting in %.1fs.",
                name,
                retry_delay_seconds,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log_exception(
                logger,
                "%s failed; restarting in %.1fs: %s",
                name,
                retry_delay_seconds,
                exc,
            )

        await asyncio.sleep(retry_delay_seconds)
