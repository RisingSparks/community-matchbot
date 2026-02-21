from __future__ import annotations

from matchbot.db import engine as engine_module
from matchbot.settings import Settings


def test_to_async_db_url_converts_standard_postgres_url() -> None:
    url = "postgresql://user:pass@host.neon.tech:5432/dbname?sslmode=require"
    converted = engine_module._to_async_db_url(url)
    assert converted == "postgresql+asyncpg://user:pass@host.neon.tech:5432/dbname?sslmode=require"


def test_to_async_db_url_leaves_existing_async_url_unchanged() -> None:
    url = "postgresql+asyncpg://user:pass@host.neon.tech:5432/dbname?sslmode=require"
    assert engine_module._to_async_db_url(url) == url


def test_get_engine_prefers_neon_database_url(monkeypatch) -> None:
    engine_module._engine = None
    settings = Settings(
        database_backend="neon",
        db_path="matchbot.db",
        neon_database_url="postgresql://user:pass@host.neon.tech:5432/dbname?sslmode=require",
    )
    captured: dict[str, str | bool] = {}

    def fake_create_async_engine(url: str, echo: bool = False):
        captured["url"] = url
        captured["echo"] = echo
        return object()

    monkeypatch.setattr(engine_module, "get_settings", lambda: settings)
    monkeypatch.setattr(engine_module, "create_async_engine", fake_create_async_engine)

    engine_module.get_engine()

    assert captured["url"] == "postgresql+asyncpg://user:pass@host.neon.tech:5432/dbname?sslmode=require"
    assert captured["echo"] is False
    engine_module._engine = None


def test_get_engine_uses_sqlite_when_neon_database_url_not_set(monkeypatch) -> None:
    engine_module._engine = None
    settings = Settings(database_backend="sqlite", db_path="local.db", neon_database_url="")
    captured: dict[str, str | bool] = {}

    def fake_create_async_engine(url: str, echo: bool = False):
        captured["url"] = url
        captured["echo"] = echo
        return object()

    monkeypatch.setattr(engine_module, "get_settings", lambda: settings)
    monkeypatch.setattr(engine_module, "create_async_engine", fake_create_async_engine)

    engine_module.get_engine()

    assert captured["url"] == "sqlite+aiosqlite:///local.db"
    assert captured["echo"] is False
    engine_module._engine = None


def test_get_engine_uses_sqlite_when_backend_is_sqlite_even_if_neon_url_exists(monkeypatch) -> None:
    engine_module._engine = None
    settings = Settings(
        database_backend="sqlite",
        db_path="local.db",
        neon_database_url="postgresql://user:pass@host.neon.tech:5432/dbname?sslmode=require",
    )
    captured: dict[str, str | bool] = {}

    def fake_create_async_engine(url: str, echo: bool = False):
        captured["url"] = url
        captured["echo"] = echo
        return object()

    monkeypatch.setattr(engine_module, "get_settings", lambda: settings)
    monkeypatch.setattr(engine_module, "create_async_engine", fake_create_async_engine)

    engine_module.get_engine()

    assert captured["url"] == "sqlite+aiosqlite:///local.db"
    assert captured["echo"] is False
    engine_module._engine = None


def test_get_engine_raises_if_neon_backend_without_neon_url(monkeypatch) -> None:
    engine_module._engine = None
    settings = Settings(database_backend="neon", db_path="local.db", neon_database_url="")

    monkeypatch.setattr(engine_module, "get_settings", lambda: settings)

    try:
        engine_module.get_engine()
    except ValueError as exc:
        assert "DATABASE_BACKEND is set to 'neon'" in str(exc)
    else:
        raise AssertionError(
            "Expected ValueError when neon backend is enabled without NEON_DATABASE_URL"
        )
