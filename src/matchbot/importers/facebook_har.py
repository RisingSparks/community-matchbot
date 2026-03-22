"""HAR and Extension JSON parser for Facebook Group historical posts."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlmodel import select

from matchbot.db.engine import get_session
from matchbot.db.models import Platform, Post, PostStatus
from matchbot.extraction import process_post
from matchbot.extraction.anthropic_extractor import AnthropicExtractor
from matchbot.extraction.openai_extractor import OpenAIExtractor
from matchbot.settings import get_settings

logger = logging.getLogger(__name__)
_RAW_POST_COMMIT_BATCH_SIZE = 100
_COMMENT_NODE_KEYS = {
    "bizweb_comment_info",
    "comment_action_links",
    "comment_direct_parent",
    "comment_menu_tooltip",
    "community_comment_signal_renderer",
    "group_comment_info",
}


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
    counts = {
        "parsed": len(post_fields_list),
        "new_candidates": 0,
        "deduped": 0,
        "before_cutoff": 0,
        "matched": 0,
        "skipped": 0,
        "extracted": 0,
        "raw_after_error": 0,
    }

    extractor = None
    if not dry_run and not no_extract:
        extractor = _get_extractor()

    try:
        async with get_session() as session:
            pending_raw_commits = 0
            for fields in post_fields_list:
                # 1. Filter by date
                if since_datetime and fields["source_created_at"] < since_datetime:
                    counts["before_cutoff"] += 1
                    continue

                # 2. DB Dedup
                existing = (
                    await session.exec(
                        select(Post.id).where(
                            Post.platform == Platform.FACEBOOK,
                            Post.platform_post_id == fields["platform_post_id"],
                        )
                    )
                ).first()

                if existing:
                    counts["deduped"] += 1
                    continue

                counts["new_candidates"] += 1

                if dry_run:
                    continue

                # Prepare Post object
                source_community = f"Facebook Group: {group_name}"
                if group_id:
                    source_community += f" ({group_id})"

                # Fallback URL if missing
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
                    title=fields["raw_text"][:80],
                    raw_text=fields["raw_text"][:2000],
                    status=PostStatus.RAW,
                )

                session.add(post)
                await session.flush()

                if no_extract:
                    pending_raw_commits += 1
                    if pending_raw_commits >= _RAW_POST_COMMIT_BATCH_SIZE:
                        await session.commit()
                        pending_raw_commits = 0
                    continue

                # 3. Process (classify + extract)
                try:
                    # process_post handles keyword filtering (SKIPPED vs INDEXED)
                    await process_post(session, post, extractor, on_extraction_error="raw")
                    if post.status == PostStatus.INDEXED:
                        counts["matched"] += 1
                        counts["extracted"] += 1
                    elif post.status == PostStatus.SKIPPED:
                        counts["skipped"] += 1
                    elif post.status == PostStatus.RAW:
                        counts["raw_after_error"] += 1
                except Exception as exc:
                    logger.error("Extraction error for post %s: %s", post.platform_post_id, exc)
                    counts["raw_after_error"] += 1
                    # Keep as RAW for manual retry later

                if sleep_seconds > 0:
                    await asyncio.sleep(sleep_seconds)

            if pending_raw_commits > 0:
                await session.commit()

    finally:
        if extractor:
            await extractor.aclose()

    return counts
