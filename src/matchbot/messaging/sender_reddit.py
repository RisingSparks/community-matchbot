"""Reddit DM sender (moderator-triggered only)."""

from __future__ import annotations

import asyncpraw

from matchbot.db.models import Match, Post
from matchbot.messaging.renderer import render_intro
from matchbot.settings import get_settings


async def send_reddit_intro(seeker: Post, camp: Post, match: Match) -> None:
    """Send an intro DM to the seeker via Reddit."""
    settings = get_settings()
    intro_text = render_intro(seeker, camp, "reddit")

    async with asyncpraw.Reddit(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        user_agent=settings.reddit_user_agent,
        username=settings.reddit_username,
        password=settings.reddit_password,
    ) as reddit:
        recipient = seeker.platform_author_id or seeker.author_display_name
        subject = "A Burning Man camp connection — just a warm intro"
        await reddit.redditor(recipient).message(subject=subject, message=intro_text)
