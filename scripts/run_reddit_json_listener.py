#!/usr/bin/env python
"""Entry point: start Reddit JSON poller only."""

import asyncio
import logging
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from matchbot.db.engine import create_db_and_tables
from matchbot.listeners.reddit_json import run_reddit_json_listener
from matchbot.log_config import configure_logging
from matchbot.settings import get_settings

logger = logging.getLogger("matchbot.reddit_json")


def create_health_app() -> FastAPI:
    app = FastAPI(title="Matchbot Reddit Poller Health")

    @app.get("/")
    @app.get("/health")
    @app.get("/status")
    async def health() -> dict[str, str]:
        return {"status": "ok", "message": "Matchbot Poller is running."}

    return app


async def main() -> None:
    settings = get_settings()
    verbose = configure_logging(settings.verbose)

    await create_db_and_tables()
    logger.info("Database ready.")

    uvicorn_config = uvicorn.Config(
        create_health_app(),
        host=settings.server_host,
        port=settings.server_port,
        loop="asyncio",
        log_level="debug" if verbose else "warning",
    )
    server = uvicorn.Server(uvicorn_config)

    async with asyncio.TaskGroup() as tg:
        tg.create_task(server.serve(), name="healthcheck-server")
        tg.create_task(run_reddit_json_listener(), name="reddit-json-listener")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested — exiting.")
