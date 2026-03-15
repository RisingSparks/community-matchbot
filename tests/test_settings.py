"""Tests for Settings validation."""

import pytest
from pydantic import ValidationError

from matchbot.settings import Settings


def neon(**kwargs) -> Settings:
    return Settings(_env_file=None, database_backend="neon", **kwargs)


# ---------------------------------------------------------------------------
# Neon validation
# ---------------------------------------------------------------------------


def test_neon_requires_url():
    with pytest.raises(ValidationError, match="NEON_DATABASE_URL is not set"):
        neon(neon_database_url="")


def test_neon_rejects_bad_scheme():
    with pytest.raises(ValidationError, match="got scheme"):
        neon(neon_database_url="mysql://user:pass@host.example.com/db")


def test_neon_rejects_missing_hostname():
    with pytest.raises(ValidationError, match="must include a hostname"):
        neon(neon_database_url="postgresql://")


def test_neon_accepts_postgresql_url():
    s = neon(neon_database_url="postgresql://user:pass@ep-cool.us-east-2.aws.neon.tech/db")
    assert s.database_backend == "neon"


def test_neon_accepts_postgres_alias():
    s = neon(neon_database_url="postgres://user:pass@ep-cool.us-east-2.aws.neon.tech/db")
    assert s.database_backend == "neon"


def test_neon_accepts_asyncpg_url():
    s = neon(neon_database_url="postgresql+asyncpg://user:pass@ep-cool.us-east-2.aws.neon.tech/db")
    assert s.database_backend == "neon"


def test_sqlite_does_not_require_neon_url():
    s = Settings(_env_file=None, database_backend="sqlite", neon_database_url="")
    assert s.database_backend == "sqlite"


# ---------------------------------------------------------------------------
# Storage settings
# ---------------------------------------------------------------------------


def test_raw_data_dir_default(reset_settings):
    from matchbot.settings import get_settings

    settings = get_settings()
    assert settings.raw_data_dir == "data/raw"
