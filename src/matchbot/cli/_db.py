"""Shared sync DB helper for CLI commands (Typer is sync; we run async in asyncio.run)."""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from sqlmodel.ext.asyncio.session import AsyncSession

from matchbot.db.engine import dispose_engine
from matchbot.db.engine import get_session

T = TypeVar("T")


def run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine from a sync Typer command."""
    return asyncio.run(coro)


async def _with_session[T](fn: Callable[[AsyncSession], Coroutine[Any, Any, T]]) -> T:
    try:
        async with get_session() as session:
            return await fn(session)
    finally:
        await dispose_engine()


def with_session[T](fn: Callable[[AsyncSession], Coroutine[Any, Any, T]]) -> T:
    """Run an async function that receives a DB session."""
    return run_async(_with_session(fn))
