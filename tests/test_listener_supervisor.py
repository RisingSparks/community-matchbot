from __future__ import annotations

import asyncio

import pytest

from matchbot.listeners.supervisor import run_forever


@pytest.mark.asyncio
async def test_run_forever_retries_after_failure() -> None:
    attempts = 0
    reached_second_attempt = asyncio.Event()

    async def flaky_listener() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("boom")
        reached_second_attempt.set()
        await asyncio.sleep(0)

    task = asyncio.create_task(run_forever("demo-listener", flaky_listener, retry_delay_seconds=0))

    await asyncio.wait_for(reached_second_attempt.wait(), timeout=1)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert attempts >= 2
