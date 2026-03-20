from __future__ import annotations

import importlib

import pytest
import typer

backfill_script = importlib.import_module("scripts.backfill_reddit_json")


@pytest.mark.asyncio
async def test_main_async_creates_tables_without_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_create_db_and_tables() -> None:
        calls.append("create")

    async def fake_reset_db_and_tables() -> None:
        calls.append("reset")

    async def fake_backfill_reddit_json(*args, **kwargs) -> dict[str, int]:
        calls.append("backfill")
        return {
            "pages": 1,
            "fetched": 2,
            "new_candidates": 2,
            "matched": 1,
            "skipped": 1,
            "deduped": 0,
            "extracted": 1,
            "raw_after_error": 0,
        }

    async def fake_dispose_engine() -> None:
        calls.append("dispose")

    monkeypatch.setattr(backfill_script, "create_db_and_tables", fake_create_db_and_tables)
    monkeypatch.setattr(backfill_script, "reset_db_and_tables", fake_reset_db_and_tables)
    monkeypatch.setattr(backfill_script, "backfill_reddit_json", fake_backfill_reddit_json)
    monkeypatch.setattr(backfill_script, "dispose_engine", fake_dispose_engine)

    await backfill_script._main_async(
        since_date="2026-01-01",
        reset_db=False,
        yes=False,
        fetch_limit=25,
        sleep_seconds=0.0,
        max_pages=10,
        dry_run=False,
        live=True,
    )

    assert calls == ["create", "backfill", "dispose"]


@pytest.mark.asyncio
async def test_main_async_resets_tables_when_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_create_db_and_tables() -> None:
        calls.append("create")

    async def fake_reset_db_and_tables() -> None:
        calls.append("reset")

    async def fake_backfill_reddit_json(*args, **kwargs) -> dict[str, int]:
        calls.append("backfill")
        return {
            "pages": 1,
            "fetched": 2,
            "new_candidates": 2,
            "matched": 1,
            "skipped": 1,
            "deduped": 0,
            "extracted": 1,
            "raw_after_error": 0,
        }

    async def fake_dispose_engine() -> None:
        calls.append("dispose")

    monkeypatch.setattr(backfill_script, "create_db_and_tables", fake_create_db_and_tables)
    monkeypatch.setattr(backfill_script, "reset_db_and_tables", fake_reset_db_and_tables)
    monkeypatch.setattr(backfill_script, "backfill_reddit_json", fake_backfill_reddit_json)
    monkeypatch.setattr(backfill_script, "dispose_engine", fake_dispose_engine)

    await backfill_script._main_async(
        since_date="2026-01-01",
        reset_db=True,
        yes=True,
        fetch_limit=25,
        sleep_seconds=0.0,
        max_pages=10,
        dry_run=False,
        live=True,
    )

    assert calls == ["reset", "backfill", "dispose"]


@pytest.mark.asyncio
async def test_main_async_aborts_when_reset_not_confirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_create_db_and_tables() -> None:
        raise AssertionError("create_db_and_tables should not run when reset is aborted")

    async def fake_reset_db_and_tables() -> None:
        raise AssertionError("reset_db_and_tables should not run when reset is aborted")

    async def fake_backfill_reddit_json(*args, **kwargs) -> dict[str, int]:
        raise AssertionError("backfill_reddit_json should not run when reset is aborted")

    async def fake_dispose_engine() -> None:
        raise AssertionError("dispose_engine should not run when reset is aborted")

    monkeypatch.setattr(backfill_script.typer, "confirm", lambda *args, **kwargs: False)
    monkeypatch.setattr(backfill_script, "create_db_and_tables", fake_create_db_and_tables)
    monkeypatch.setattr(backfill_script, "reset_db_and_tables", fake_reset_db_and_tables)
    monkeypatch.setattr(backfill_script, "backfill_reddit_json", fake_backfill_reddit_json)
    monkeypatch.setattr(backfill_script, "dispose_engine", fake_dispose_engine)

    with pytest.raises(typer.Abort):
        await backfill_script._main_async(
            since_date="2026-01-01",
            reset_db=True,
            yes=False,
            fetch_limit=25,
            sleep_seconds=0.0,
            max_pages=10,
            dry_run=False,
            live=True,
        )
