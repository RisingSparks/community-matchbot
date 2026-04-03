from __future__ import annotations

import importlib
from datetime import UTC, datetime

import pytest
import typer

backfill_script = importlib.import_module("scripts.backfill_reddit_json")
cmd_data = importlib.import_module("matchbot.cli.cmd_data")
raw_store_module = importlib.import_module("matchbot.storage.raw_store")


def test_main_defaults_since_date_to_last_7_days(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            current = datetime(2026, 4, 3, 12, 0, 0, tzinfo=UTC)
            if tz is None:
                return current.replace(tzinfo=None)
            return current.astimezone(tz)

    class FakeSettings:
        verbose = False
        reddit_json_user_agent = "ua"
        reddit_json_emulate_browser = False
        reddit_json_cookie = None

    async def fake_main_async(**kwargs) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(backfill_script, "datetime", FixedDatetime)
    monkeypatch.setattr(backfill_script, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(backfill_script, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(backfill_script, "_main_async", fake_main_async)

    backfill_script.main(since_date=None)

    assert captured["since_date"] == "2026-03-27"


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


@pytest.mark.asyncio
async def test_backfill_from_cache_retries_existing_raw_posts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {"created_utc": 1735689600, "title": "Looking for camp"}

    class FakeStore:
        def load(self, platform: str, post_id: str):
            assert platform == "reddit"
            assert post_id == "raw01"
            return payload

    class FakeSettings:
        raw_data_dir = "ignored"

    replayed: list[str] = []

    async def fake_post_status_async(platform: str, post_ids: list[str]) -> dict[str, str | None]:
        assert platform == "reddit"
        assert post_ids == ["raw01"]
        return {"raw01": "raw"}

    async def fake_replay_one(platform: str, post_id: str, replay_payload: dict) -> None:
        assert platform == "reddit"
        assert replay_payload is payload
        replayed.append(post_id)

    monkeypatch.setattr(backfill_script, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(raw_store_module, "RawStore", lambda base_dir: FakeStore())
    monkeypatch.setattr(cmd_data, "_post_status_async", fake_post_status_async)
    monkeypatch.setattr(cmd_data, "_replay_one", fake_replay_one)

    await backfill_script._backfill_from_cache(
        ["raw01"],
        dry_run=False,
        since_datetime=datetime(2025, 1, 1, tzinfo=UTC).replace(tzinfo=None),
    )

    assert replayed == ["raw01"]


@pytest.mark.asyncio
async def test_backfill_from_cache_skips_non_raw_existing_posts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {"created_utc": 1735689600, "title": "Looking for camp"}

    class FakeStore:
        def load(self, platform: str, post_id: str):
            assert platform == "reddit"
            assert post_id == "done01"
            return payload

    class FakeSettings:
        raw_data_dir = "ignored"

    async def fake_post_status_async(platform: str, post_ids: list[str]) -> dict[str, str | None]:
        assert platform == "reddit"
        assert post_ids == ["done01"]
        return {"done01": "indexed"}

    async def fail_replay_one(platform: str, post_id: str, replay_payload: dict) -> None:
        raise AssertionError("_replay_one should not run for indexed posts")

    monkeypatch.setattr(backfill_script, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(raw_store_module, "RawStore", lambda base_dir: FakeStore())
    monkeypatch.setattr(cmd_data, "_post_status_async", fake_post_status_async)
    monkeypatch.setattr(cmd_data, "_replay_one", fail_replay_one)

    await backfill_script._backfill_from_cache(
        ["done01"],
        dry_run=False,
        since_datetime=datetime(2025, 1, 1, tzinfo=UTC).replace(tzinfo=None),
    )
