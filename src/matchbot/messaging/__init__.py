"""Messaging package — intro message rendering and sending."""

from __future__ import annotations

from sqlmodel.ext.asyncio.session import AsyncSession

from matchbot.db.models import Match, Platform, Post


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


async def send_feedback_message(
    session: AsyncSession,
    match: Match,
    seeker: Post,
    camp: Post,
) -> None:
    """Send feedback follow-up messages to both match participants."""
    platform = match.intro_platform
    if not platform:
        raise ValueError("match.intro_platform is not set — cannot send feedback")

    from matchbot.messaging.renderer import render_feedback

    if platform == Platform.REDDIT:
        from matchbot.messaging.sender_reddit import _send_reddit_dm
        seeker_text = render_feedback(seeker, camp, platform)
        await _send_reddit_dm(
            seeker.platform_author_id or seeker.author_display_name,
            "Following up on your Burning Man introduction",
            seeker_text,
        )
        camp_text = render_feedback(camp, seeker, platform)
        await _send_reddit_dm(
            camp.platform_author_id or camp.author_display_name,
            "Following up on your Burning Man introduction",
            camp_text,
        )
    elif platform == Platform.DISCORD:
        from matchbot.messaging.sender_discord import _create_dm_channel, _send_to_channel
        from matchbot.settings import get_settings
        token = get_settings().discord_bot_token

        if seeker.platform_author_id and seeker.platform_author_id.isdigit():
            seeker_text = render_feedback(seeker, camp, platform)
            ch = await _create_dm_channel(token, seeker.platform_author_id)
            await _send_to_channel(token, ch, seeker_text)

        if camp.platform_author_id and camp.platform_author_id.isdigit():
            camp_text = render_feedback(camp, seeker, platform)
            ch = await _create_dm_channel(token, camp.platform_author_id)
            await _send_to_channel(token, ch, camp_text)
    elif platform == Platform.FACEBOOK:
        from matchbot.messaging.sender_facebook import _send_fb_message
        from matchbot.settings import get_settings
        token = get_settings().facebook_page_access_token

        if seeker.platform_author_id:
            seeker_text = render_feedback(seeker, camp, platform)
            await _send_fb_message(token, seeker.platform_author_id, seeker_text)

        if camp.platform_author_id:
            camp_text = render_feedback(camp, seeker, platform)
            await _send_fb_message(token, camp.platform_author_id, camp_text)
    else:
        raise ValueError(f"Unknown platform for feedback: {platform!r}")
