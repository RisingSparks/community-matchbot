"""Discord DM sender (moderator-triggered only).

Uses the Discord REST API directly to avoid spinning up a new gateway client
per send, which would conflict with the long-running listener bot on the same token.
"""

from __future__ import annotations

import httpx

from matchbot.db.models import Match, Post
from matchbot.messaging.renderer import render_intro
from matchbot.settings import get_settings

_DISCORD_API_BASE = "https://discord.com/api/v10"


async def _create_dm_channel(token: str, user_id: str) -> str:
    """Open a DM channel with a user and return the channel ID."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_DISCORD_API_BASE}/users/@me/channels",
            headers={"Authorization": f"Bot {token}"},
            json={"recipient_id": user_id},
        )
        resp.raise_for_status()
        return resp.json()["id"]


async def _send_to_channel(token: str, channel_id: str, content: str) -> None:
    """Post a message to an existing channel."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_DISCORD_API_BASE}/channels/{channel_id}/messages",
            headers={"Authorization": f"Bot {token}"},
            json={"content": content},
        )
        resp.raise_for_status()


async def send_discord_intro(seeker: Post, camp: Post, match: Match) -> None:
    """Send intro DMs to both seeker and camp contact via Discord REST API."""
    settings = get_settings()
    token = settings.discord_bot_token

    if seeker.platform_author_id and seeker.platform_author_id.isdigit():
        seeker_text = render_intro(seeker, camp, "discord", for_camp=False)
        seeker_channel = await _create_dm_channel(token, seeker.platform_author_id)
        await _send_to_channel(token, seeker_channel, seeker_text)

    if camp.platform_author_id and camp.platform_author_id.isdigit():
        camp_text = render_intro(seeker, camp, "discord", for_camp=True)
        camp_channel = await _create_dm_channel(token, camp.platform_author_id)
        await _send_to_channel(token, camp_channel, camp_text)
