"""FastAPI router for Facebook Graph API webhooks."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, Request, Response
from sqlmodel import select

from matchbot.db.engine import get_session
from matchbot.db.models import Platform, Post, PostStatus
from matchbot.extraction import process_post
from matchbot.extraction.anthropic_extractor import AnthropicExtractor
from matchbot.extraction.openai_extractor import OpenAIExtractor
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
                await _handle_feed_change(change.get("value", {}))

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
        await process_post(session, post, extractor)
