import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

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
    """Ensure URLs use an async SQLAlchemy dialect."""
    if db_url.startswith("postgres://"):
        return f"postgresql+asyncpg://{db_url.removeprefix('postgres://')}"
    if db_url.startswith("postgresql://"):
        return f"postgresql+asyncpg://{db_url.removeprefix('postgresql://')}"
    return db_url


settings = get_settings()
if settings.database_backend == "neon":
    if not settings.neon_database_url:
        raise ValueError("DATABASE_BACKEND is set to 'neon' but NEON_DATABASE_URL is empty.")
    sqlalchemy_url = _to_async_db_url(settings.neon_database_url)
else:
    sqlalchemy_url = f"sqlite+aiosqlite:///{settings.db_path}"
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
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
