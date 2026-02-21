"""Facebook Messenger sender via Graph API (moderator-triggered only)."""

from __future__ import annotations

import httpx

from matchbot.db.models import Match, Post
from matchbot.messaging.renderer import render_intro
from matchbot.settings import get_settings

_FB_API_URL = "https://graph.facebook.com/v19.0/me/messages"


async def send_facebook_intro(seeker: Post, camp: Post, match: Match) -> None:
    """Send an intro message to the seeker via Facebook Messenger."""
    settings = get_settings()
    intro_text = render_intro(seeker, camp, "facebook")

    recipient_id = seeker.platform_author_id
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": intro_text},
        "messaging_type": "RESPONSE",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _FB_API_URL,
            params={"access_token": settings.facebook_page_access_token},
            json=payload,
        )
        resp.raise_for_status()
