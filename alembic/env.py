import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlmodel import SQLModel

# Import all models so SQLModel metadata is populated
import matchbot.db.models  # noqa: F401
from matchbot.settings import get_settings

# this is the Alembic Config object
config = context.config

def _to_sync_db_url(db_url: str) -> str:
    """Ensure Postgres URLs use a sync SQLAlchemy dialect for Alembic."""
    if db_url.startswith("postgresql+asyncpg://"):
        return f"postgresql://{db_url.removeprefix('postgresql+asyncpg://')}"
    if db_url.startswith("postgres://"):
        return f"postgresql://{db_url.removeprefix('postgres://')}"
    return db_url


settings = get_settings()
if settings.database_backend == "neon":
    if not settings.neon_database_url:
        raise ValueError("DATABASE_BACKEND is set to 'neon' but NEON_DATABASE_URL is empty.")
    sqlalchemy_url = _to_sync_db_url(settings.neon_database_url)
else:
    sqlalchemy_url = f"sqlite:///{settings.db_path}"
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


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
