import asyncio
import logging
import sys
from logging.config import fileConfig
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from alembic.script import ScriptDirectory
from sqlalchemy import exc as sa_exc
from sqlalchemy import inspect, pool, text
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
logger = logging.getLogger("alembic.env")


def _table_has_column(db_inspector, table_name: str, column_name: str) -> bool:
    try:
        return any(column["name"] == column_name for column in db_inspector.get_columns(table_name))
    except sa_exc.SQLAlchemyError:  # pragma: no cover - defensive for reflection issues
        return False


def _missing_tables_and_columns(db_inspector) -> tuple[list[str], list[str]]:
    existing_tables = set(db_inspector.get_table_names())
    model_tables = {
        table_name: table
        for table_name, table in target_metadata.tables.items()
        if table_name != "alembic_version"
    }

    missing_tables = sorted(
        table_name for table_name in model_tables if table_name not in existing_tables
    )
    missing_columns: list[str] = []

    for table_name, table in model_tables.items():
        if table_name in missing_tables:
            continue
        for column in table.columns:
            if not _table_has_column(db_inspector, table_name, column.name):
                missing_columns.append(f"{table_name}.{column.name}")

    return missing_tables, missing_columns


def _schema_matches_current_models(db_inspector) -> bool:
    missing_tables, missing_columns = _missing_tables_and_columns(db_inspector)
    return not missing_tables and not missing_columns


def _stamp_head_if_needed(connection) -> None:
    db_inspector = inspect(connection)
    if "alembic_version" in set(db_inspector.get_table_names()):
        return
    if not _schema_matches_current_models(db_inspector):
        return

    head_revision = ScriptDirectory.from_config(config).get_current_head()
    connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS alembic_version "
            "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
        )
    )
    connection.execute(text("DELETE FROM alembic_version"))
    connection.execute(
        text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
        {"revision": head_revision},
    )
    logger.info(
        "Detected pre-existing schema without alembic_version; stamped database to revision %s",
        head_revision,
    )


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
    _stamp_head_if_needed(connection)
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(
        sqlalchemy_url,
        connect_args=connect_args,
        poolclass=pool.NullPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
