#!/usr/bin/env python
"""Entry point: start Reddit JSON poller only."""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from matchbot.db.engine import create_db_and_tables
from matchbot.listeners.reddit_json import run_reddit_json_listener
from matchbot.log_config import configure_logging
from matchbot.settings import get_settings

logger = logging.getLogger("matchbot.reddit_json")


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.verbose)

    await create_db_and_tables()
    logger.info("Database ready.")

    await run_reddit_json_listener()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested — exiting.")
