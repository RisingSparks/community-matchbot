"""Reddit JSON poller for unauthenticated stage-1 ingestion."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any, Literal

import httpx
from sqlalchemy.exc import ProgrammingError
from sqlmodel import select

from matchbot.backfill import log_backfill_progress, new_backfill_counts
from matchbot.db.engine import (
    create_db_and_tables,
    dispose_engine,
    get_session,
    is_disconnect_error,
)
from matchbot.db.models import Platform, Post, PostStatus
from matchbot.extraction import process_post
from matchbot.extraction.anthropic_extractor import AnthropicExtractor
from matchbot.extraction.keywords import keyword_filter
from matchbot.extraction.openai_extractor import OpenAIExtractor
from matchbot.log_config import log_exception
from matchbot.settings import get_settings
from matchbot.storage.raw_store import RawStore

logger = logging.getLogger(__name__)

_raw_store: RawStore | None = None
_REDDIT_DB_RETRY_ATTEMPTS = 3


def _get_raw_store() -> RawStore:
    global _raw_store
    if _raw_store is None:
        _raw_store = RawStore(base_dir=get_settings().raw_data_dir)
    return _raw_store


_REDDIT_NEW_URL = "https://www.reddit.com/r/BurningMan/new.json"
_REDDIT_NEW_URL_FALLBACK = "https://old.reddit.com/r/BurningMan/new.json"
_REDDIT_COMMUNITY = "BurningMan"
_REDDIT_BLOCK_RETRY_DELAY_SECONDS = 30.0
_IngestOutcome = Literal[
    "ignored",
    "deduped",
    "skipped",
    "matched_extracted",
    "matched_raw_after_error",
    "dryrun_skipped",
    "dryrun_matched",
]


def _is_missing_table_error(exc: Exception) -> bool:
    if not isinstance(exc, ProgrammingError):
        return False
    return "UndefinedTableError" in str(exc) or 'relation "post" does not exist' in str(exc)


def _get_extractor():
    settings = get_settings()
    if settings.llm_provider == "openai":
        return OpenAIExtractor()
    return AnthropicExtractor()


def _build_source_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return f"https://reddit.com{url}"
    return f"https://reddit.com/{url}"


def _source_created_at_from_json(data: dict[str, Any]) -> datetime | None:
    created_utc = data.get("created_utc")
    if created_utc is None:
        return None
    try:
        return datetime.fromtimestamp(float(created_utc), UTC).replace(tzinfo=None)
    except (TypeError, ValueError, OSError):
        return None


async def _latest_reddit_post_id() -> str | None:
    async def _load_latest() -> str | None:
        async with get_session() as session:
            row = (
                await session.exec(
                    select(Post.platform_post_id)
                    .where(
                        Post.platform == Platform.REDDIT,
                        Post.source_community == _REDDIT_COMMUNITY,
                    )
                    .order_by(Post.detected_at.desc())
                    .limit(1)
                )
            ).first()
        return row if row else None

    return await _run_reddit_db_retry("latest checkpoint", _load_latest)


async def _get_existing_post(platform_post_id: str) -> Post | None:
    async def _load_existing() -> Post | None:
        async with get_session() as session:
            return (
                await session.exec(
                    select(Post).where(
                        Post.platform == Platform.REDDIT,
                        Post.platform_post_id == platform_post_id,
                    )
                )
            ).first()

    return await _run_reddit_db_retry(f"load post {platform_post_id}", _load_existing)


async def _post_exists(platform_post_id: str) -> bool:
    return await _get_existing_post(platform_post_id) is not None


async def _run_reddit_db_retry[T](
    operation_name: str,
    callback,
    *,
    max_attempts: int = _REDDIT_DB_RETRY_ATTEMPTS,
) -> T:
    for attempt in range(1, max_attempts + 1):
        try:
            return await callback()
        except Exception as exc:
            if attempt >= max_attempts or not is_disconnect_error(exc):
                raise
            backoff_seconds = 0.2 * attempt
            logger.warning(
                "Transient DB disconnect during Reddit %s (attempt %d/%d). Retrying in %.1fs.",
                operation_name,
                attempt,
                max_attempts,
                backoff_seconds,
            )
            await dispose_engine()
            await asyncio.sleep(backoff_seconds)

    raise RuntimeError(f"Unreachable retry termination for Reddit {operation_name}.")


def _build_reddit_json_headers() -> dict[str, str]:
    settings = get_settings()
    user_agent = settings.reddit_json_user_agent or settings.reddit_user_agent

    if not settings.reddit_json_emulate_browser:
        return {
            "User-Agent": user_agent,
            "Accept": "application/json",
        }

    headers = {
        "User-Agent": user_agent,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,"
            "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Priority": "u=0, i",
        "Sec-CH-UA": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": '"macOS"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }
    if settings.reddit_json_cookie:
        headers["Cookie"] = settings.reddit_json_cookie
    return headers


def _is_block_status(status_code: int) -> bool:
    return status_code in {403, 429}


def _retry_delay_seconds(response: httpx.Response) -> float:
    retry_after = response.headers.get("Retry-After")
    if isinstance(retry_after, (str, int, float)) and retry_after != "":
        try:
            parsed = float(retry_after)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return _REDDIT_BLOCK_RETRY_DELAY_SECONDS


async def _fetch_reddit_json_page(
    client: httpx.AsyncClient,
    *,
    limit: int,
    after: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"limit": limit, "raw_json": 1}
    if after:
        params["after"] = after

    response = await client.get(_REDDIT_NEW_URL, params=params)
    if _is_block_status(response.status_code):
        delay = _retry_delay_seconds(response)
        logger.warning(
            (
                "Reddit JSON endpoint returned %s from %s; "
                "sleeping %.1fs before retrying via fallback endpoint. "
                "Set REDDIT_JSON_USER_AGENT to a descriptive value "
                "(e.g. 'matchbot/0.1 by u/<username>')."
            ),
            response.status_code,
            _REDDIT_NEW_URL,
            delay,
        )
        await asyncio.sleep(delay)
        response = await client.get(_REDDIT_NEW_URL_FALLBACK, params=params)
        if _is_block_status(response.status_code):
            delay = _retry_delay_seconds(response)
            logger.warning(
                (
                    "Reddit fallback JSON endpoint returned %s from %s; "
                    "treating this poll as blocked so outer backoff can engage. "
                    "Suggested retry delay: %.1fs."
                ),
                response.status_code,
                _REDDIT_NEW_URL_FALLBACK,
                delay,
            )

    response.raise_for_status()
    return response.json()


def _apply_outcome(counts: dict[str, int], outcome: _IngestOutcome) -> None:
    if outcome == "deduped":
        counts["deduped"] += 1
    elif outcome in {"skipped", "dryrun_skipped"}:
        counts["skipped"] += 1
    elif outcome in {"matched_extracted", "matched_raw_after_error", "dryrun_matched"}:
        counts["matched"] += 1
        if outcome == "matched_extracted":
            counts["extracted"] += 1
        elif outcome == "matched_raw_after_error":
            counts["raw_after_error"] += 1


async def _ingest_reddit_json_item(
    data: dict[str, Any],
    extractor: Any | None,
    *,
    dry_run: bool,
) -> tuple[_IngestOutcome, Any | None]:
    post_id = data.get("id")
    if not post_id:
        return "ignored", extractor

    # Persist the raw API payload before any transformation or truncation.
    _get_raw_store().save("reddit", datetime.now(UTC).date().isoformat(), post_id, data)

    title = (data.get("title") or "")[:500]
    body = (data.get("selftext") or "")[:2000]
    kw_result = keyword_filter(title, body)
    if dry_run:
        return ("dryrun_matched" if kw_result.tier != "no_match" else "dryrun_skipped"), extractor

    author_id = data.get("author_fullname") or data.get("author") or "unknown"
    author_display = data.get("author") or author_id
    permalink = data.get("permalink") or ""
    source_url = _build_source_url(
        permalink
        or data.get("url_overridden_by_dest")
        or data.get("url")
    )

    if extractor is None:
        extractor = _get_extractor()

    async def _ingest_once() -> _IngestOutcome:
        existing = await _get_existing_post(post_id)
        if existing is not None:
            if existing.status == PostStatus.RAW:
                async with get_session() as session:
                    post = await session.get(Post, existing.id)
                    assert post is not None
                    before_status = post.status
                    post = await process_post(
                        session,
                        post,
                        extractor,
                        on_extraction_error="raw",
                    )
                    if post.status == PostStatus.RAW and before_status == PostStatus.RAW:
                        return "matched_raw_after_error"
                    return "matched_extracted"
            return "deduped"

        async with get_session() as session:
            if kw_result.tier == "no_match":
                post = Post(
                    platform=Platform.REDDIT,
                    platform_post_id=post_id,
                    platform_author_id=author_id,
                    author_display_name=author_display,
                    source_url=source_url,
                    source_community=_REDDIT_COMMUNITY,
                    title=title,
                    raw_text=body,
                    source_created_at=_source_created_at_from_json(data),
                    status=PostStatus.SKIPPED,
                    extraction_method="keyword",
                )
                post.post_type = None
                session.add(post)
                await session.commit()
                return "skipped"

            post = Post(
                platform=Platform.REDDIT,
                platform_post_id=post_id,
                platform_author_id=author_id,
                author_display_name=author_display,
                source_url=source_url,
                source_community=_REDDIT_COMMUNITY,
                title=title,
                raw_text=body,
                source_created_at=_source_created_at_from_json(data),
                status=PostStatus.RAW,
            )
            session.add(post)
            await session.commit()
            await session.refresh(post)

            before_status = post.status
            post = await process_post(
                session,
                post,
                extractor,
                on_extraction_error="raw",
            )
            if post.status == PostStatus.RAW and before_status == PostStatus.RAW:
                return "matched_raw_after_error"
            return "matched_extracted"

    outcome = await _run_reddit_db_retry(f"ingest post {post_id}", _ingest_once)
    return outcome, extractor


async def _ingest_reddit_json_batch(
    items: list[dict[str, Any]],
    *,
    dry_run: bool,
    max_concurrency: int,
) -> list[_IngestOutcome]:
    if not items:
        return []

    concurrency = max(1, max_concurrency)
    if concurrency == 1:
        outcomes: list[_IngestOutcome] = []
        extractor = None
        try:
            for data in items:
                outcome, extractor = await _ingest_reddit_json_item(
                    data,
                    extractor,
                    dry_run=dry_run,
                )
                outcomes.append(outcome)
        finally:
            if extractor is not None:
                await extractor.aclose()
        return outcomes

    semaphore = asyncio.Semaphore(concurrency)

    async def _run_one(data: dict[str, Any]) -> _IngestOutcome:
        async with semaphore:
            extractor = None
            try:
                outcome, extractor = await _ingest_reddit_json_item(
                    data,
                    extractor,
                    dry_run=dry_run,
                )
                return outcome
            finally:
                if extractor is not None:
                    await extractor.aclose()

    return list(await asyncio.gather(*(_run_one(data) for data in items)))


async def poll_reddit_json_once(client: httpx.AsyncClient | None = None) -> dict[str, int]:
    """Poll Reddit JSON once and ingest posts newer than the latest stored post."""
    settings = get_settings()

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(
            timeout=30,
            headers=_build_reddit_json_headers(),
        )

    counts = new_backfill_counts()

    try:
        checkpoint_id = await _latest_reddit_post_id()

        payload = await _fetch_reddit_json_page(
            client,
            limit=settings.reddit_json_fetch_limit,
        )

        children = payload.get("data", {}).get("children", [])
        counts["fetched"] = len(children)

        new_items: list[dict[str, Any]] = []
        for child in children:
            data = child.get("data", {})
            post_id = data.get("id")
            if not post_id:
                continue
            if checkpoint_id and post_id == checkpoint_id:
                break
            new_items.append(data)

        counts["new_candidates"] = len(new_items)

        outcomes = await _ingest_reddit_json_batch(
            list(reversed(new_items)),
            dry_run=False,
            max_concurrency=settings.reddit_json_max_concurrent_extractions,
        )
        for outcome in outcomes:
            _apply_outcome(counts, outcome)

        return counts
    finally:
        if owns_client and client is not None:
            await client.aclose()


async def backfill_reddit_json(
    since_datetime: datetime,
    *,
    fetch_limit: int | None = None,
    sleep_seconds: float = 1.5,
    max_pages: int = 500,
    dry_run: bool = False,
    client: httpx.AsyncClient | None = None,
) -> dict[str, int]:
    """Page through historical Reddit JSON posts and ingest posts on/after a cutoff."""
    if max_pages < 1:
        raise ValueError("max_pages must be >= 1")

    settings = get_settings()
    limit = fetch_limit or settings.reddit_json_fetch_limit

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(
            timeout=30,
            headers=_build_reddit_json_headers(),
        )

    counts = new_backfill_counts(extra_keys=("pages",))
    counts["pages"] = 0
    started_at = time.monotonic()

    after: str | None = None
    reached_cutoff = False
    fetch_backoff = _REDDIT_BLOCK_RETRY_DELAY_SECONDS
    try:
        for _ in range(max_pages):
            while True:
                try:
                    payload = await _fetch_reddit_json_page(
                        client,
                        limit=limit,
                        after=after,
                    )
                    fetch_backoff = _REDDIT_BLOCK_RETRY_DELAY_SECONDS
                    break
                except httpx.HTTPStatusError as exc:
                    status_code = exc.response.status_code if exc.response is not None else None
                    if status_code is None or not _is_block_status(status_code):
                        raise
                    suggested_delay = (
                        _retry_delay_seconds(exc.response)
                        if exc.response is not None
                        else _REDDIT_BLOCK_RETRY_DELAY_SECONDS
                    )
                    delay = max(fetch_backoff, suggested_delay)
                    logger.warning(
                        (
                            "Reddit JSON backfill fetch blocked with %s; "
                            "sleeping %.1fs before retrying the same page."
                        ),
                        status_code,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    fetch_backoff = min(delay * 2, 600.0)
            counts["pages"] += 1
            logger.debug("Fetched page %d (after=%r).", counts["pages"], after)

            children = payload.get("data", {}).get("children", [])
            counts["fetched"] += len(children)

            in_scope: list[dict[str, Any]] = []
            for child in children:
                data = child.get("data", {})
                post_id = data.get("id")
                if not post_id:
                    continue
                created_at = _source_created_at_from_json(data)
                if created_at is not None and created_at < since_datetime:
                    reached_cutoff = True
                    break
                in_scope.append(data)

            counts["new_candidates"] += len(in_scope)

            outcomes = await _ingest_reddit_json_batch(
                list(reversed(in_scope)),
                dry_run=dry_run,
                max_concurrency=settings.reddit_json_max_concurrent_extractions,
            )
            for outcome in outcomes:
                _apply_outcome(counts, outcome)

            log_backfill_progress(
                logger,
                label="Reddit JSON backfill",
                counts=counts,
                started_at=started_at,
                extra={"after": after, "reached_cutoff": reached_cutoff},
            )

            if reached_cutoff:
                break

            after = payload.get("data", {}).get("after")
            if not after:
                break

            if sleep_seconds > 0:
                logger.debug(
                    "Page %d done; sleeping %.1fs before next page.",
                    counts["pages"],
                    sleep_seconds,
                )
                await asyncio.sleep(sleep_seconds)

        return counts
    finally:
        if owns_client and client is not None:
            await client.aclose()


async def run_reddit_json_listener() -> None:
    """Poll Reddit JSON at a fixed interval with reconnect/backoff behavior."""
    settings = get_settings()
    if not settings.reddit_json_enabled:
        logger.info("Reddit JSON listener disabled (REDDIT_JSON_ENABLED=false).")
        return

    backoff = 30

    while True:
        try:
            counts = await poll_reddit_json_once()
            logger.info(
                (
                    "Reddit JSON poll complete: fetched=%d new=%d matched=%d "
                    "skipped=%d deduped=%d raw_after_error=%d"
                ),
                counts["fetched"],
                counts["new_candidates"],
                counts["matched"],
                counts["skipped"],
                counts["deduped"],
                counts["raw_after_error"],
            )
            backoff = 30
            await asyncio.sleep(settings.reddit_json_poll_interval_seconds)
        except asyncio.CancelledError:
            logger.info("Reddit JSON listener cancelled.")
            return
        except Exception as exc:
            if _is_missing_table_error(exc):
                logger.warning("Missing DB tables detected; bootstrapping schema before retry.")
                await create_db_and_tables()
                backoff = 5
                await asyncio.sleep(backoff)
                continue
            if is_disconnect_error(exc):
                logger.warning(
                    "Transient DB disconnect detected; disposing engine and retrying in %ss.",
                    5,
                )
                await dispose_engine()
                backoff = 5
                await asyncio.sleep(backoff)
                continue
            log_exception(
                logger,
                "Reddit JSON listener error: %s - retrying in %ss",
                exc,
                backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 600)
