from __future__ import annotations

import pytest
from pydantic import ValidationError

from matchbot.settings import Settings


def test_neon_requires_url() -> None:
    with pytest.raises(ValidationError, match="NEON_DATABASE_URL is not set"):
        Settings.model_validate(
            {"database_backend": "neon", "neon_database_url": ""},
            context={"_env_file": None},
        )


def test_neon_accepts_postgresql_scheme() -> None:
    s = Settings.model_validate(
        {
            "database_backend": "neon",
            "neon_database_url": "postgresql://user:pass@host.neon.tech:5432/dbname",
        },
        context={"_env_file": None},
    )
    assert s.database_backend == "neon"


def test_neon_accepts_postgres_scheme() -> None:
    s = Settings.model_validate(
        {
            "database_backend": "neon",
            "neon_database_url": "postgres://user:pass@host.neon.tech:5432/dbname",
        },
        context={"_env_file": None},
    )
    assert s.database_backend == "neon"


def test_neon_accepts_asyncpg_scheme() -> None:
    s = Settings.model_validate(
        {
            "database_backend": "neon",
            "neon_database_url": "postgresql+asyncpg://user:pass@host.neon.tech:5432/dbname",
        },
        context={"_env_file": None},
    )
    assert s.database_backend == "neon"


def test_neon_rejects_unsupported_scheme() -> None:
    with pytest.raises(ValidationError, match="unsupported scheme"):
        Settings.model_validate(
            {
                "database_backend": "neon",
                "neon_database_url": "mysql://user:pass@host/dbname",
            },
            context={"_env_file": None},
        )


def test_sqlite_does_not_require_neon_url() -> None:
    s = Settings.model_validate(
        {"database_backend": "sqlite"},
        context={"_env_file": None},
    )
    assert s.database_backend == "sqlite"
