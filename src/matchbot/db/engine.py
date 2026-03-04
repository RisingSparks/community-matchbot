from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from urllib.parse import urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from matchbot.settings import get_settings

_engine: AsyncEngine | None = None


def _to_async_db_url(db_url: str) -> str:
    """Convert to asyncpg dialect, stripping libpq-specific query params."""
    if db_url.startswith("postgresql://"):
        db_url = f"postgresql+asyncpg://{db_url.removeprefix('postgresql://')}"
    elif db_url.startswith("postgres://"):
        db_url = f"postgresql+asyncpg://{db_url.removeprefix('postgres://')}"
    # Strip all query params — asyncpg doesn't understand libpq params like
    # sslmode, channel_binding, etc. SSL is passed via connect_args instead.
    parsed = urlparse(db_url)
    return urlunparse(parsed._replace(query=""))


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        if settings.database_backend == "neon":
            if not settings.neon_database_url:
                raise ValueError(
                    "DATABASE_BACKEND is set to 'neon' but NEON_DATABASE_URL is empty."
                )
            db_url = _to_async_db_url(settings.neon_database_url)
            connect_args = {"ssl": True}
            engine_kwargs = {
                "pool_pre_ping": True,
                "pool_recycle": 1800,
            }
        else:
            db_url = f"sqlite+aiosqlite:///{settings.db_path}"
            connect_args = {}
            engine_kwargs = {}
        _engine = create_async_engine(
            db_url,
            connect_args=connect_args,
            echo=False,
            **engine_kwargs,
        )
    return _engine


async def dispose_engine() -> None:
    """Dispose the global async engine and clear pooled connections."""
    global _engine
    if _engine is None:
        return
    await _engine.dispose()
    _engine = None


async def create_db_and_tables() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
