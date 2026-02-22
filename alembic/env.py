import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlmodel import SQLModel

# Import all models so SQLModel metadata is populated
import matchbot.db.models  # noqa: F401
from matchbot.settings import get_settings

# this is the Alembic Config object
config = context.config


def _to_async_db_url(db_url: str) -> str:
    """Convert to asyncpg dialect, stripping libpq-specific query params."""
    if db_url.startswith("postgres://"):
        db_url = f"postgresql+asyncpg://{db_url.removeprefix('postgres://')}"
    elif db_url.startswith("postgresql://"):
        db_url = f"postgresql+asyncpg://{db_url.removeprefix('postgresql://')}"
    # Strip all query params — asyncpg doesn't understand libpq params like
    # sslmode, channel_binding, etc. SSL is passed via connect_args instead.
    parsed = urlparse(db_url)
    return urlunparse(parsed._replace(query=""))


settings = get_settings()
if settings.database_backend == "neon":
    if not settings.neon_database_url:
        raise ValueError("DATABASE_BACKEND is set to 'neon' but NEON_DATABASE_URL is empty.")
    sqlalchemy_url = _to_async_db_url(settings.neon_database_url)
    connect_args: dict = {"ssl": True}
else:
    sqlalchemy_url = f"sqlite+aiosqlite:///{settings.db_path}"
    connect_args = {}

config.set_main_option("sqlalchemy.url", sqlalchemy_url)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(
        sqlalchemy_url,
        connect_args=connect_args,
        poolclass=pool.NullPool,
    )
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
