"""Shared sync DB helper for CLI commands (Typer is sync; we run async in asyncio.run)."""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from sqlmodel.ext.asyncio.session import AsyncSession

from matchbot.db.engine import get_session

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine from a sync Typer command."""
    return asyncio.run(coro)


async def _with_session(fn: Callable[[AsyncSession], Coroutine[Any, Any, T]]) -> T:
    async with get_session() as session:
        return await fn(session)


def with_session(fn: Callable[[AsyncSession], Coroutine[Any, Any, T]]) -> T:
    """Run an async function that receives a DB session."""
    return run_async(_with_session(fn))
