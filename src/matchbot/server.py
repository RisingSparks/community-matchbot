"""FastAPI app factory — mounts Facebook webhook router + health check."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response

from matchbot.branding import (
    BRAND_LOGO_FILE,
    BRAND_LOGO_PATH,
    FAVICON_PATH,
    WEBMANIFEST_PATH,
)
from pathlib import Path

from matchbot.forms.router import router as forms_router
from matchbot.listeners.facebook import router as facebook_router
from matchbot.log_config import configure_logging
from matchbot.mod.router import router as mod_router
from matchbot.public.router import community_home
from matchbot.public.router import router as community_router


def _build_lifespan(run_migrations_on_startup: bool):
    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        """Run migrations, then start scheduler on startup; shut it down on shutdown."""
        from matchbot.db.engine import dispose_engine
        from matchbot.db.migrations import upgrade_db_to_head
        from matchbot.scheduler import create_scheduler

        if run_migrations_on_startup:
            await upgrade_db_to_head()

        scheduler = create_scheduler()
        scheduler.start()
        try:
            yield
        finally:
            scheduler.shutdown(wait=False)
            await dispose_engine()

    return _lifespan


def create_app(enable_scheduler: bool = True, run_migrations_on_startup: bool = True) -> FastAPI:
    configure_logging()
    lifespan = _build_lifespan(run_migrations_on_startup) if enable_scheduler else None
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
    app.include_router(community_router)

    assets_dir = Path(__file__).resolve().parent / "assets"

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request) -> str:
        return await community_home(request)

    @app.get(FAVICON_PATH, include_in_schema=False)
    async def favicon() -> Response:
        return FileResponse(assets_dir / "favicon.ico", media_type="image/x-icon")

    @app.get(WEBMANIFEST_PATH, include_in_schema=False)
    async def webmanifest() -> Response:
        return FileResponse(assets_dir / "site.webmanifest", media_type="application/manifest+json")

    @app.get(BRAND_LOGO_PATH, include_in_schema=False)
    async def brand_logo() -> Response:
        return FileResponse(BRAND_LOGO_FILE, media_type="image/png")

    @app.get("/health")
    @app.get("/status")
    async def health() -> dict[str, str]:
        return {"status": "ok", "message": "Matchbot API is running."}

    return app


app = create_app()
