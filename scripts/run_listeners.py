#!/usr/bin/env python
"""
Entry point: start all three platform listeners concurrently.

Usage:
    uv run python scripts/run_listeners.py
"""

import asyncio
import logging
import sys
from pathlib import Path

import uvicorn

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from matchbot.db.engine import create_db_and_tables
from matchbot.listeners.discord_bot import run_discord_bot
from matchbot.listeners.reddit import run_reddit_inbox_listener, run_reddit_listener
from matchbot.log_config import configure_logging
from matchbot.server import create_app
from matchbot.settings import get_settings

logger = logging.getLogger("matchbot.run")


async def main() -> None:
    settings = get_settings()
    verbose = configure_logging(settings.verbose)

    # Initialize DB schema
    await create_db_and_tables()
    logger.info("Database ready.")

    # Configure uvicorn for the Facebook webhook server
    fastapi_app = create_app()
    uvicorn_config = uvicorn.Config(
        fastapi_app,
        host=settings.server_host,
        port=settings.server_port,
        loop="asyncio",
        ws="websockets-sansio",
        log_level="debug" if verbose else "warning",
    )
    server = uvicorn.Server(uvicorn_config)

    logger.info("Starting all listeners…")

    async with asyncio.TaskGroup() as tg:
        if not settings.reddit_enabled:
            logger.info("Reddit disabled (REDDIT_ENABLED=false) — skipping Reddit listeners.")
        elif not settings.reddit_configured:
            logger.info("Reddit credentials not set — skipping Reddit listeners.")
        else:
            tg.create_task(run_reddit_listener(), name="reddit-listener")
            tg.create_task(run_reddit_inbox_listener(), name="reddit-inbox-listener")

        if not settings.discord_enabled:
            logger.info("Discord disabled (DISCORD_ENABLED=false) — skipping Discord listener.")
        elif not settings.discord_configured:
            logger.info("Discord credentials not set — skipping Discord listener.")
        else:
            tg.create_task(run_discord_bot(), name="discord-bot")

        tg.create_task(server.serve(), name="facebook-webhook")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested — exiting.")
