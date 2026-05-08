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

from matchbot.db.engine import dispose_engine
from matchbot.db.migrations import upgrade_db_to_head
from matchbot.listeners.discord_bot import run_discord_bot
from matchbot.listeners.reddit import run_reddit_inbox_listener, run_reddit_listener
from matchbot.listeners.supervisor import run_forever
from matchbot.log_config import configure_logging
from matchbot.server import create_app
from matchbot.settings import get_settings

logger = logging.getLogger("matchbot.run")


async def main() -> None:
    settings = get_settings()
    verbose = configure_logging(settings.verbose)

    await upgrade_db_to_head()
    logger.info("Database migrated to head.")

    # Configure uvicorn for the Facebook webhook server
    fastapi_app = create_app(run_migrations_on_startup=False)
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

    listener_tasks: list[asyncio.Task[None]] = []
    try:
        server_task = asyncio.create_task(server.serve(), name="facebook-webhook")

        if not settings.reddit_enabled:
            logger.info("Reddit disabled (REDDIT_ENABLED=false) — skipping Reddit listeners.")
        elif not settings.reddit_configured:
            logger.info("Reddit credentials not set — skipping Reddit listeners.")
        else:
            listener_tasks.append(
                asyncio.create_task(
                    run_forever("reddit-listener", run_reddit_listener),
                    name="reddit-listener",
                )
            )
            listener_tasks.append(
                asyncio.create_task(
                    run_forever("reddit-inbox-listener", run_reddit_inbox_listener),
                    name="reddit-inbox-listener",
                )
            )

        if not settings.discord_enabled:
            logger.info("Discord disabled (DISCORD_ENABLED=false) — skipping Discord listener.")
        elif not settings.discord_configured:
            logger.info("Discord credentials not set — skipping Discord listener.")
        else:
            listener_tasks.append(
                asyncio.create_task(
                    run_forever("discord-bot", run_discord_bot),
                    name="discord-bot",
                )
            )

        await server_task
    finally:
        for task in listener_tasks:
            task.cancel()
        if listener_tasks:
            await asyncio.gather(*listener_tasks, return_exceptions=True)
        await dispose_engine()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested — exiting.")
