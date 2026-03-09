from __future__ import annotations

import asyncio
from pathlib import Path

from alembic.config import Config
from sqlalchemy import inspect
from sqlmodel import SQLModel

from alembic import command


def _alembic_config() -> Config:
    repo_root = Path(__file__).resolve().parents[3]
    config = Config(str(repo_root / "alembic.ini"))
    config.set_main_option("script_location", str(repo_root / "alembic"))
    return config


def _upgrade_db_to_head_sync() -> None:
    command.upgrade(_alembic_config(), "head")


def _missing_tables_and_columns(connection) -> tuple[list[str], list[str]]:
    db_inspector = inspect(connection)
    existing_tables = set(db_inspector.get_table_names())
    model_tables = {
        table_name: table
        for table_name, table in SQLModel.metadata.tables.items()
        if table_name != "alembic_version"
    }

    missing_tables = sorted(
        table_name for table_name in model_tables if table_name not in existing_tables
    )
    missing_columns: list[str] = []

    for table_name, table in model_tables.items():
        if table_name in missing_tables:
            continue
        existing_columns = {column["name"] for column in db_inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name not in existing_columns:
                missing_columns.append(f"{table_name}.{column.name}")

    return missing_tables, missing_columns


async def _validate_schema_matches_models() -> None:
    import matchbot.db.models  # noqa: F401
    from matchbot.db.engine import get_engine

    async with get_engine().connect() as connection:
        missing_tables, missing_columns = await connection.run_sync(_missing_tables_and_columns)

    if not missing_tables and not missing_columns:
        return

    details: list[str] = []
    if missing_tables:
        details.append(f"missing tables: {', '.join(missing_tables)}")
    if missing_columns:
        details.append(f"missing columns: {', '.join(missing_columns)}")

    raise RuntimeError(
        "Database schema does not match current models after Alembic migration. "
        + "; ".join(details)
    )


async def upgrade_db_to_head() -> None:
    """Run Alembic migrations to head in a worker thread."""
    await asyncio.to_thread(_upgrade_db_to_head_sync)
    await _validate_schema_matches_models()
