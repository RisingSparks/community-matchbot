"""Discord DM sender (moderator-triggered only)."""

from __future__ import annotations

import discord

from matchbot.db.models import Match, Post
from matchbot.messaging.renderer import render_intro
from matchbot.settings import get_settings


async def send_discord_intro(seeker: Post, camp: Post, match: Match) -> None:
    """Send an intro DM to the seeker via Discord."""
    settings = get_settings()
    intro_text = render_intro(seeker, camp, "discord")

    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        try:
            user_id = int(seeker.platform_author_id)
            user = await client.fetch_user(user_id)
            await user.send(content=intro_text)
        finally:
            await client.close()

    await client.start(settings.discord_bot_token)
