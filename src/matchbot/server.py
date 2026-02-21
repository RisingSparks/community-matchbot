"""FastAPI app factory — mounts Facebook webhook router + health check."""

from __future__ import annotations

from fastapi import FastAPI

from matchbot.listeners.facebook import router as facebook_router


def create_app() -> FastAPI:
    app = FastAPI(title="Matchbot API", version="0.1.0")

    app.include_router(facebook_router)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
