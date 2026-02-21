"""Messaging package — intro message rendering and sending."""

from __future__ import annotations

from matchbot.db.models import Match, Post
from matchbot.db.models import Platform
from sqlmodel.ext.asyncio.session import AsyncSession


async def send_intro_message(
    session: AsyncSession,
    match: Match,
    seeker: Post,
    camp: Post,
    platform: str,
) -> None:
    """Dispatch intro message to the appropriate platform sender."""
    if platform == Platform.REDDIT:
        from matchbot.messaging.sender_reddit import send_reddit_intro
        await send_reddit_intro(seeker, camp, match)
    elif platform == Platform.DISCORD:
        from matchbot.messaging.sender_discord import send_discord_intro
        await send_discord_intro(seeker, camp, match)
    elif platform == Platform.FACEBOOK:
        from matchbot.messaging.sender_facebook import send_facebook_intro
        await send_facebook_intro(seeker, camp, match)
    else:
        raise ValueError(f"Unknown platform for intro: {platform!r}")
