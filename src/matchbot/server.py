"""FastAPI app factory — mounts Facebook webhook router + health check."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from matchbot.forms.router import router as forms_router
from matchbot.listeners.facebook import router as facebook_router
from matchbot.log_config import configure_logging
from matchbot.mod.router import router as mod_router


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Start scheduler on startup; shut it down on shutdown."""
    from matchbot.scheduler import create_scheduler

    scheduler = create_scheduler()
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


def create_app(enable_scheduler: bool = True) -> FastAPI:
    configure_logging()
    lifespan = _lifespan if enable_scheduler else None
    app = FastAPI(title="Matchbot API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://matchbotmod.rising-sparks.org"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(facebook_router)
    app.include_router(forms_router)
    app.include_router(mod_router)

    @app.get("/")
    @app.get("/health")
    @app.get("/status")
    async def health() -> dict:
        return {"status": "ok", "message": "Matchbot API is running."}

    return app


app = create_app()
