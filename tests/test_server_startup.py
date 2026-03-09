from __future__ import annotations

from fastapi.testclient import TestClient

from matchbot import scheduler as scheduler_module
from matchbot.db import engine as engine_module
from matchbot.db import migrations as migrations_module
from matchbot.server import create_app


def test_app_startup_runs_migrations_before_scheduler(monkeypatch) -> None:
    calls: list[str] = []

    class FakeScheduler:
        def start(self) -> None:
            calls.append("start")

        def shutdown(self, wait: bool = False) -> None:
            assert wait is False
            calls.append("shutdown")

    async def fake_upgrade() -> None:
        calls.append("upgrade")

    async def fake_dispose() -> None:
        calls.append("dispose")

    monkeypatch.setattr(migrations_module, "upgrade_db_to_head", fake_upgrade)
    monkeypatch.setattr(engine_module, "dispose_engine", fake_dispose)
    monkeypatch.setattr(scheduler_module, "create_scheduler", lambda: FakeScheduler())

    with TestClient(create_app()) as client:
        response = client.get("/health")

        assert response.status_code == 200
        assert calls == ["upgrade", "start"]

    assert calls == ["upgrade", "start", "shutdown", "dispose"]


def test_app_startup_can_skip_migrations(monkeypatch) -> None:
    calls: list[str] = []

    class FakeScheduler:
        def start(self) -> None:
            calls.append("start")

        def shutdown(self, wait: bool = False) -> None:
            assert wait is False
            calls.append("shutdown")

    async def fake_upgrade() -> None:
        calls.append("upgrade")

    async def fake_dispose() -> None:
        calls.append("dispose")

    monkeypatch.setattr(migrations_module, "upgrade_db_to_head", fake_upgrade)
    monkeypatch.setattr(engine_module, "dispose_engine", fake_dispose)
    monkeypatch.setattr(scheduler_module, "create_scheduler", lambda: FakeScheduler())

    with TestClient(create_app(run_migrations_on_startup=False)) as client:
        response = client.get("/health")

        assert response.status_code == 200
        assert calls == ["start"]

    assert calls == ["start", "shutdown", "dispose"]
