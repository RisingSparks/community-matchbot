"""FastAPI router for Facebook Graph API webhooks."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, Request, Response
from sqlmodel import select

from matchbot.db.engine import get_session
from matchbot.db.models import OptOut, Platform, Post, PostStatus
from matchbot.extraction import process_post
from matchbot.extraction.anthropic_extractor import AnthropicExtractor
from matchbot.extraction.openai_extractor import OpenAIExtractor
from matchbot.log_config import log_exception
from matchbot.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook")


def _get_extractor():
    settings = get_settings()
    if settings.llm_provider == "openai":
        return OpenAIExtractor()
    return AnthropicExtractor()


@router.get("/facebook")
async def facebook_verify(request: Request) -> Response:
    """Facebook webhook verification handshake."""
    settings = get_settings()
    params = request.query_params

    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.facebook_verify_token:
        logger.info("Facebook webhook verified.")
        return Response(content=challenge, media_type="text/plain")

    logger.warning("Facebook webhook verification failed. mode=%s token_match=%s", mode, token == settings.facebook_verify_token)
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/facebook")
async def facebook_event(request: Request) -> dict:
    """Facebook webhook event handler."""
    settings = get_settings()
    body = await request.body()

    # Validate HMAC-SHA256 signature
    signature_header = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_signature(body, settings.facebook_app_secret, signature_header):
        raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") == "feed":
                # Fire-and-forget: Facebook requires a 200 response within 20 seconds.
                # LLM extraction can exceed that, so defer processing to a background task.
                asyncio.ensure_future(_handle_feed_change(change.get("value", {})))
            elif change.get("field") == "messages":
                asyncio.ensure_future(_handle_messages_change(change.get("value", {})))

    return {"status": "ok"}


def _verify_signature(body: bytes, app_secret: str, signature_header: str) -> bool:
    """Verify the X-Hub-Signature-256 header."""
    if not app_secret:
        # Skip verification if no secret configured (dev mode)
        return True
    if not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        app_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


async def _handle_feed_change(value: dict) -> None:
    """Process a Facebook feed change event."""
    message = value.get("message", "")
    sender = value.get("from", {})
    platform_post_id = value.get("post_id") or value.get("id") or f"fb_{uuid.uuid4().hex[:12]}"
    permalink = value.get("permalink_url", "")
    group_id = value.get("group_id", "")
    sender_id = sender.get("id", "")
    sender_name = sender.get("name", "")

    if not message:
        return

    async with get_session() as session:
        existing = (
            await session.exec(
                select(Post).where(
                    Post.platform == Platform.FACEBOOK,
                    Post.platform_post_id == platform_post_id,
                )
            )
        ).first()
        if existing:
            return

        post = Post(
            platform=Platform.FACEBOOK,
            platform_post_id=platform_post_id,
            platform_author_id=sender_id,
            author_display_name=sender_name,
            source_url=permalink,
            source_community=f"Facebook Group: {group_id}",
            title=message[:80],
            raw_text=message[:2000],
            status=PostStatus.RAW,
        )
        session.add(post)
        await session.commit()
        await session.refresh(post)

        extractor = _get_extractor()
        try:
            await process_post(session, post, extractor)
        finally:
            await extractor.aclose()


async def _handle_messages_change(value: dict) -> None:
    """Handle a Facebook Messenger message event (for opt-out)."""
    sender_id = value.get("sender", {}).get("id", "")
    text = value.get("message", {}).get("text", "")

    if not sender_id or not text:
        return

    if text.strip().lower() == "opt out":
        async with get_session() as session:
            opt_out = OptOut(
                platform=Platform.FACEBOOK,
                platform_author_id=sender_id,
            )
            session.add(opt_out)
            await session.commit()
        logger.info("Facebook user %s opted out.", sender_id)

        # Send confirmation via Messenger
        try:
            settings = get_settings()
            from matchbot.messaging.sender_facebook import _send_fb_message
            await _send_fb_message(
                settings.facebook_page_access_token,
                sender_id,
                "You've been opted out of future introductions. "
                "You won't receive any more match messages from us.",
            )
        except Exception as exc:
            log_exception(
                logger,
                "Failed to send Facebook opt-out confirmation to %s: %s",
                sender_id,
                exc,
            )
