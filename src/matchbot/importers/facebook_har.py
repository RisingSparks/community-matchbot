"""HAR and Extension JSON parser for Facebook Group historical posts."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlmodel import select

from matchbot.backfill import log_backfill_progress, new_backfill_counts, should_log_progress
from matchbot.db.engine import dispose_engine, get_session, is_disconnect_error
from matchbot.db.models import Platform, Post, PostStatus
from matchbot.extraction import process_post
from matchbot.extraction.anthropic_extractor import AnthropicExtractor
from matchbot.extraction.openai_extractor import OpenAIExtractor
from matchbot.settings import get_settings
from matchbot.title_utils import build_source_title

logger = logging.getLogger(__name__)
_FACEBOOK_BACKFILL_DB_RETRY_ATTEMPTS = 3
_FACEBOOK_BACKFILL_PROGRESS_EVERY = 10
_COMMENT_NODE_KEYS = {
    "bizweb_comment_info",
    "comment_action_links",
    "comment_direct_parent",
    "comment_menu_tooltip",
    "community_comment_signal_renderer",
    "group_comment_info",
}
_NOISE_PATTERNS = (
    "let's welcome our new members",
    "lets welcome our new members",
    "welcome our new members",
    "welcome our newest members",
    "please welcome our new members",
)


def _looks_like_noise_post(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    return any(pattern in normalized for pattern in _NOISE_PATTERNS)


def _extract_story_message_text(node: dict) -> str:
    content = node.get("comet_sections")
    if not isinstance(content, dict):
        return ""

    content_section = content.get("content")
    if not isinstance(content_section, dict):
        return ""

    story = content_section.get("story")
    if not isinstance(story, dict):
        return ""

    story_sections = story.get("comet_sections")
    if not isinstance(story_sections, dict):
        return ""

    for key in ("message", "message_container"):
        section = story_sections.get(key)
        if not isinstance(section, dict):
            continue
        section_story = section.get("story")
        if not isinstance(section_story, dict):
            continue
        message = section_story.get("message")
        if isinstance(message, dict) and isinstance(message.get("text"), str):
            return message["text"]

    return ""


def _extract_story_creation_time(node: dict) -> Any:
    comet_sections = node.get("comet_sections")
    if not isinstance(comet_sections, dict):
        return None

    timestamp_section = comet_sections.get("timestamp")
    if not isinstance(timestamp_section, dict):
        return None

    story = timestamp_section.get("story")
    if not isinstance(story, dict):
        return None

    return story.get("creation_time")


def _extract_story_url(node: dict) -> str:
    if isinstance(node.get("permalink_url"), str):
        return node["permalink_url"]

    comet_sections = node.get("comet_sections")
    if not isinstance(comet_sections, dict):
        return ""

    timestamp_section = comet_sections.get("timestamp")
    if not isinstance(timestamp_section, dict):
        return ""

    story = timestamp_section.get("story")
    if not isinstance(story, dict):
        return ""

    url = story.get("url")
    return url if isinstance(url, str) else ""


def _find_post_nodes(obj: Any, depth: int = 0) -> list[dict]:
    """Recursively walk a JSON object, return dicts that look like Facebook posts."""
    if depth > 20:
        return []

    nodes = []
    if isinstance(obj, dict):
        # Check if this dict itself looks like a post
        if _is_post_node(obj):
            return [obj]

        # Otherwise, recurse into values
        for value in obj.values():
            nodes.extend(_find_post_nodes(value, depth + 1))
    elif isinstance(obj, list):
        for item in obj:
            nodes.extend(_find_post_nodes(item, depth + 1))

    return nodes


def _is_post_node(node: dict) -> bool:
    """Determine if a dictionary node looks like a Facebook post."""
    platform_id = node.get("post_id") or node.get("id")

    # Must have some form of ID
    if not platform_id:
        return False

    # Exclude comment nodes that otherwise look post-like in GraphQL payloads.
    typename = str(node.get("__typename") or "")
    if (
        isinstance(platform_id, str)
        and (
            platform_id.startswith("comment:")
            or platform_id.startswith("Y29tbWVudDo")
        )
    ) or "Comment" in typename:
        return False
    if any(key in node for key in _COMMENT_NODE_KEYS):
        return False

    # Must have some form of timestamp
    if not (
        node.get("creation_time")
        or node.get("created_time")
        or _extract_story_creation_time(node)
    ):
        return False

    # Must have some form of text content (even if empty, but usually not)
    # We'll be more specific in parse_facebook_post_fields
    has_text = (
        isinstance(node.get("message"), (str, dict))
        or (isinstance(node.get("body"), dict) and "text" in node["body"])
        or bool(_extract_story_message_text(node))
    )
    if not has_text:
        return False

    return True


def parse_facebook_post_fields(node: dict) -> dict | None:
    """Extract standard fields from a post node, supporting multiple shapes."""
    # Text extraction
    raw_text = ""
    message = node.get("message")
    if isinstance(message, str):
        raw_text = message
    elif isinstance(message, dict) and "text" in message:
        raw_text = message["text"]
    elif isinstance(node.get("body"), dict) and "text" in node["body"]:
        raw_text = node["body"]["text"]
    elif story_text := _extract_story_message_text(node):
        raw_text = story_text

    if not raw_text:
        return None

    if _looks_like_noise_post(raw_text):
        return None

    # ID extraction
    platform_post_id = node.get("post_id") or node.get("id")
    if not platform_post_id:
        return None

    # Strip 'post:' prefix if present (Relay style)
    if isinstance(platform_post_id, str) and platform_post_id.startswith("post:"):
        platform_post_id = platform_post_id.replace("post:", "", 1)

    # Timestamp extraction
    created_ts = (
        node.get("creation_time")
        or node.get("created_time")
        or _extract_story_creation_time(node)
    )
    if not created_ts:
        return None

    try:
        source_created_at = datetime.fromtimestamp(float(created_ts), tz=UTC).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None

    # Author extraction
    author_id = ""
    author_name = ""

    # GraphQL Relay style: actors[0]
    actors = node.get("actors")
    if isinstance(actors, list) and len(actors) > 0:
        author_id = actors[0].get("id", "")
        author_name = actors[0].get("name", author_id)

    # Webhook style: from
    if not author_id:
        sender = node.get("from")
        if isinstance(sender, dict):
            author_id = sender.get("id", "")
            author_name = sender.get("name", author_id)

    # URL extraction
    source_url = node.get("permalink_url") or node.get("url") or _extract_story_url(node) or ""

    return {
        "platform_post_id": str(platform_post_id),
        "platform_author_id": str(author_id),
        "author_display_name": author_name,
        "source_url": source_url,
        "raw_text": raw_text,
        "source_created_at": source_created_at,
    }


def parse_har_file(path: Path) -> list[dict]:
    """Load a HAR file and extract all Facebook post nodes."""
    try:
        with open(path, "rb") as f:
            har_data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load HAR file %s: %s", path, exc)
        return []

    all_posts = []
    entries = har_data.get("log", {}).get("entries", [])
    for entry in entries:
        url = entry.get("request", {}).get("url", "")
        if "/api/graphql" not in url:
            continue

        content = entry.get("response", {}).get("content", {})
        text = content.get("text")
        if not text:
            continue

        if content.get("encoding") == "base64":
            try:
                text = base64.b64decode(text).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError) as exc:
                logger.debug("Failed to decode base64 content in HAR: %s", exc)
                continue

        # GraphQL responses can be JSONL (multiple JSON objects separated by newline)
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                post_nodes = _find_post_nodes(obj)
                for node in post_nodes:
                    fields = parse_facebook_post_fields(node)
                    if fields:
                        all_posts.append(fields)
            except json.JSONDecodeError:
                continue

    # Deduplicate by platform_post_id
    unique_posts = {}
    for p in all_posts:
        unique_posts[p["platform_post_id"]] = p

    return list(unique_posts.values())


def parse_extension_json(path: Path) -> list[dict]:
    """Load an extension-style JSON and extract posts.

    Supports both the original format:
      ["raw response text", ...]

    and the richer format emitted by the hardened extension:
      [{"seq": 1, "capturedAt": "...", "text": "raw response text"}, ...]
    """
    try:
        with open(path, "rb") as f:
            responses = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load extension JSON %s: %s", path, exc)
        return []

    if not isinstance(responses, list):
        logger.error("Extension JSON %s is not a list", path)
        return []

    all_posts = []
    for item in responses:
        text = item
        if isinstance(item, dict):
            text = item.get("text")
        if not isinstance(text, str):
            continue
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                post_nodes = _find_post_nodes(obj)
                for node in post_nodes:
                    fields = parse_facebook_post_fields(node)
                    if fields:
                        all_posts.append(fields)
            except json.JSONDecodeError:
                continue

    unique_posts = {}
    for p in all_posts:
        unique_posts[p["platform_post_id"]] = p

    return list(unique_posts.values())


def _get_extractor():
    settings = get_settings()
    if settings.llm_provider == "openai":
        return OpenAIExtractor()
    return AnthropicExtractor()


async def _run_facebook_backfill_db_op[T](
    platform_post_id: str,
    callback,
    *,
    max_attempts: int = _FACEBOOK_BACKFILL_DB_RETRY_ATTEMPTS,
) -> T:
    for attempt in range(1, max_attempts + 1):
        try:
            async with get_session() as session:
                return await callback(session)
        except Exception as exc:
            if attempt >= max_attempts or not is_disconnect_error(exc):
                raise
            backoff_seconds = 0.2 * attempt
            logger.warning(
                (
                    "Transient DB disconnect while processing Facebook post %s "
                    "(attempt %d/%d). Retrying in %.1fs."
                ),
                platform_post_id,
                attempt,
                max_attempts,
                backoff_seconds,
            )
            await dispose_engine()
            await asyncio.sleep(backoff_seconds)

    raise RuntimeError(f"Unreachable retry termination for Facebook post {platform_post_id}.")


async def _process_existing_or_new_facebook_post(
    session,
    *,
    fields: dict,
    group_name: str,
    group_id: str | None,
    dry_run: bool,
    no_extract: bool,
    extractor,
) -> str:
    existing = (
        await session.exec(
            select(Post).where(
                Post.platform == Platform.FACEBOOK,
                Post.platform_post_id == fields["platform_post_id"],
            )
        )
    ).first()

    if existing:
        if existing.status == PostStatus.RAW and not dry_run and not no_extract:
            try:
                await process_post(session, existing, extractor, on_extraction_error="raw")
                if existing.status == PostStatus.INDEXED:
                    return "matched_extracted"
                if existing.status == PostStatus.SKIPPED:
                    return "skipped"
                if existing.status == PostStatus.RAW:
                    return "raw_after_error"
                return "deduped"
            except Exception:
                await session.rollback()
                raise
        return "deduped"

    if dry_run:
        return "new_candidate"

    source_community = f"Facebook Group: {group_name}"
    if group_id:
        source_community += f" ({group_id})"

    source_url = fields["source_url"]
    if not source_url and group_id:
        source_url = f"https://www.facebook.com/groups/{group_id}/posts/{fields['platform_post_id']}"

    post = Post(
        platform=Platform.FACEBOOK,
        platform_post_id=fields["platform_post_id"],
        platform_author_id=fields["platform_author_id"],
        author_display_name=fields["author_display_name"],
        source_url=source_url,
        source_community=source_community,
        source_created_at=fields["source_created_at"],
        title=build_source_title("", fields["raw_text"]),
        raw_text=fields["raw_text"][:2000],
        status=PostStatus.RAW,
    )

    session.add(post)
    await session.flush()

    if no_extract:
        await session.commit()
        return "new_candidate"

    try:
        await process_post(session, post, extractor, on_extraction_error="raw")
        if post.status == PostStatus.INDEXED:
            return "matched_extracted"
        if post.status == PostStatus.SKIPPED:
            return "skipped"
        if post.status == PostStatus.RAW:
            return "raw_after_error"
        return "new_candidate"
    except Exception:
        await session.rollback()
        raise


async def backfill_facebook_posts(
    post_fields_list: list[dict],
    *,
    group_name: str,
    group_id: str | None = None,
    since_datetime: datetime | None = None,
    dry_run: bool = False,
    sleep_seconds: float = 0.5,
    no_extract: bool = False,
) -> dict[str, int]:
    """Ingest a list of Facebook post fields into the database."""
    counts = new_backfill_counts()
    counts["parsed"] = len(post_fields_list)

    extractor = None
    if not dry_run and not no_extract:
        extractor = _get_extractor()

    started_at = time.monotonic()
    processed = 0
    total = len(post_fields_list)

    try:
        for fields in post_fields_list:
            processed += 1
            if since_datetime and fields["source_created_at"] < since_datetime:
                counts["before_cutoff"] += 1
                if should_log_progress(
                    processed, total, every=_FACEBOOK_BACKFILL_PROGRESS_EVERY
                ):
                    log_backfill_progress(
                        logger,
                        label=f"Facebook backfill for {group_name}",
                        counts=counts,
                        started_at=started_at,
                        processed=processed,
                        total=total,
                    )
                continue

            try:
                outcome = await _run_facebook_backfill_db_op(
                    fields["platform_post_id"],
                    lambda session: _process_existing_or_new_facebook_post(
                        session,
                        fields=fields,
                        group_name=group_name,
                        group_id=group_id,
                        dry_run=dry_run,
                        no_extract=no_extract,
                        extractor=extractor,
                    ),
                )
            except Exception as exc:
                logger.error("Extraction error for post %s: %s", fields["platform_post_id"], exc)
                counts["raw_after_error"] += 1
                if sleep_seconds > 0:
                    await asyncio.sleep(sleep_seconds)
                continue

            if outcome == "deduped":
                counts["deduped"] += 1
            elif outcome == "new_candidate":
                counts["new_candidates"] += 1
            elif outcome == "matched_extracted":
                counts["matched"] += 1
                counts["extracted"] += 1
            elif outcome == "skipped":
                counts["skipped"] += 1
            elif outcome == "raw_after_error":
                counts["raw_after_error"] += 1

            if should_log_progress(processed, total, every=_FACEBOOK_BACKFILL_PROGRESS_EVERY):
                log_backfill_progress(
                    logger,
                    label=f"Facebook backfill for {group_name}",
                    counts=counts,
                    started_at=started_at,
                    processed=processed,
                    total=total,
                )

            if sleep_seconds > 0:
                await asyncio.sleep(sleep_seconds)

    finally:
        if extractor:
            await extractor.aclose()

    return counts
