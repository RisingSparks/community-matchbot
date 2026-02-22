from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from matchbot.settings import get_settings

_engine = None


def _to_async_db_url(db_url: str) -> str:
    """Ensure Postgres URLs use the asyncpg dialect and translate SSL params."""
    if db_url.startswith("postgresql://"):
        db_url = f"postgresql+asyncpg://{db_url.removeprefix('postgresql://')}"
    elif db_url.startswith("postgres://"):
        db_url = f"postgresql+asyncpg://{db_url.removeprefix('postgres://')}"
    # asyncpg doesn't accept sslmode=; translate to ssl=require
    db_url = db_url.replace("sslmode=require", "ssl=require")
    return db_url


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
        else:
            db_url = f"sqlite+aiosqlite:///{settings.db_path}"
        _engine = create_async_engine(db_url, echo=False)
    return _engine


async def create_db_and_tables() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
