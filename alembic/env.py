import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlmodel import SQLModel

# Import all models so SQLModel metadata is populated
import matchbot.db.models  # noqa: F401

# this is the Alembic Config object
config = context.config

# Use DB_PATH env var if set (e.g. on Fly.io where DB_PATH=/data/matchbot.db)
import os
db_path = os.environ.get("DB_PATH", "matchbot.db")
config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

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
