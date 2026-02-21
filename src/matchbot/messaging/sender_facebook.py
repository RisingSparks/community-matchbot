"""Facebook Messenger sender via Graph API (moderator-triggered only)."""

from __future__ import annotations

import httpx

from matchbot.db.models import Match, Post
from matchbot.messaging.renderer import render_intro
from matchbot.settings import get_settings

_FB_API_URL = "https://graph.facebook.com/v22.0/me/messages"


async def _send_fb_message(access_token: str, recipient_id: str, text: str) -> None:
    """Send a single Facebook Messenger message."""
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
        "messaging_type": "RESPONSE",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _FB_API_URL,
            params={"access_token": access_token},
            json=payload,
        )
        resp.raise_for_status()


async def send_facebook_intro(seeker: Post, camp: Post, match: Match) -> None:
    """Send intro messages to both seeker and camp contact via Facebook Messenger."""
    settings = get_settings()
    token = settings.facebook_page_access_token

    if seeker.platform_author_id:
        seeker_text = render_intro(seeker, camp, "facebook", for_camp=False)
        await _send_fb_message(token, seeker.platform_author_id, seeker_text)

    if camp.platform_author_id:
        camp_text = render_intro(seeker, camp, "facebook", for_camp=True)
        await _send_fb_message(token, camp.platform_author_id, camp_text)
