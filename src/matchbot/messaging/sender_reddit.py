"""Reddit DM sender (moderator-triggered only)."""

from __future__ import annotations

import asyncpraw

from matchbot.db.models import Match, Post
from matchbot.messaging.renderer import render_intro
from matchbot.settings import get_settings


async def send_reddit_intro(seeker: Post, camp: Post, match: Match) -> None:
    """Send intro DMs to both the seeker and the camp contact via Reddit."""
    settings = get_settings()
    subject = "A Burning Man camp connection — just a warm intro"

    async with asyncpraw.Reddit(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        user_agent=settings.reddit_user_agent,
        username=settings.reddit_username,
        password=settings.reddit_password,
    ) as reddit:
        seeker_text = render_intro(seeker, camp, "reddit", for_camp=False)
        seeker_recipient = seeker.platform_author_id or seeker.author_display_name
        await reddit.redditor(seeker_recipient).message(subject=subject, message=seeker_text)

        camp_text = render_intro(seeker, camp, "reddit", for_camp=True)
        camp_recipient = camp.platform_author_id or camp.author_display_name
        await reddit.redditor(camp_recipient).message(subject=subject, message=camp_text)
