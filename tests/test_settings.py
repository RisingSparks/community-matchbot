"""Tests for Settings validation."""

import pytest
from pydantic import ValidationError

from matchbot.settings import Settings


def make_settings(**kwargs) -> Settings:
    """Build a Settings instance with env-file loading disabled."""
    return Settings.model_validate(
        {"database_backend": "sqlite", **kwargs},
        context={"_env_file": None},
    )


# ---------------------------------------------------------------------------
# Neon validation
# ---------------------------------------------------------------------------


def test_neon_requires_url():
    with pytest.raises(ValidationError, match="NEON_DATABASE_URL is not set"):
        Settings(database_backend="neon", neon_database_url="")


def test_neon_rejects_bad_scheme():
    with pytest.raises(ValidationError, match="must start with"):
        Settings(
            database_backend="neon",
            neon_database_url="mysql://user:pass@host.example.com/db",
        )


def test_neon_rejects_missing_hostname():
    with pytest.raises(ValidationError, match="must include a hostname"):
        Settings(
            database_backend="neon",
            neon_database_url="postgresql://",
        )


def test_neon_accepts_valid_postgresql_url():
    s = Settings(
        database_backend="neon",
        neon_database_url="postgresql://user:pass@ep-cool-name.us-east-2.aws.neon.tech/dbname",
    )
    assert s.database_backend == "neon"


def test_neon_accepts_postgres_alias():
    s = Settings(
        database_backend="neon",
        neon_database_url="postgres://user:pass@ep-cool-name.us-east-2.aws.neon.tech/dbname",
    )
    assert s.database_backend == "neon"


def test_sqlite_does_not_require_neon_url():
    s = Settings(database_backend="sqlite", neon_database_url="")
    assert s.database_backend == "sqlite"
