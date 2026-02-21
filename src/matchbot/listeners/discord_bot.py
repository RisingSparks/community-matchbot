"""Discord bot listener using discord.py."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import discord
import yaml
from discord.ext import commands
from sqlmodel import select

from matchbot.db.engine import get_session
from matchbot.db.models import Platform, Post, PostStatus
from matchbot.extraction import process_post
from matchbot.extraction.anthropic_extractor import AnthropicExtractor
from matchbot.extraction.openai_extractor import OpenAIExtractor
from matchbot.settings import get_settings

logger = logging.getLogger(__name__)

_SOURCES_PATH = Path(__file__).parent.parent.parent.parent / "config" / "sources.yaml"


def _load_discord_config() -> dict:
    with open(_SOURCES_PATH) as f:
        sources = yaml.safe_load(f)
    return sources.get("discord", {})


def _get_extractor():
    settings = get_settings()
    if settings.llm_provider == "openai":
        return OpenAIExtractor()
    return AnthropicExtractor()


def create_bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.dm_messages = True

    bot = commands.Bot(command_prefix="!", intents=intents)
    discord_config = _load_discord_config()

    # Build allowlist: {guild_id: set(channel_ids)}
    allowlist: dict[str, set[str]] = {}
    for guild_cfg in discord_config.get("guilds", []):
        gid = str(guild_cfg["guild_id"])
        channel_ids = {str(c) for c in guild_cfg.get("allowed_channel_ids", [])}
        allowlist[gid] = channel_ids

    @bot.event
    async def on_ready():
        logger.info("Discord bot connected as %s", bot.user)

    @bot.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return
        # Check allowlist
        guild_id = str(message.guild.id) if message.guild else None
        channel_id = str(message.channel.id)
        if guild_id and guild_id in allowlist:
            if channel_id not in allowlist[guild_id]:
                return  # Not in allowed channel
        elif guild_id:
            return  # Guild not in allowlist

        await _handle_discord_message(message)
        await bot.process_commands(message)

    @bot.command(name="submit")
    @commands.has_role("Moderator")
    async def submit_command(ctx: commands.Context, *, text: str):
        """Manually ingest a post (moderator only)."""
        post = Post(
            platform=Platform.MANUAL,
            platform_post_id=f"manual_{uuid.uuid4().hex[:12]}",
            platform_author_id=str(ctx.author.id),
            author_display_name=str(ctx.author.display_name),
            source_community=f"Discord: {ctx.guild.name if ctx.guild else 'DM'}",
            title=text[:80],
            raw_text=text[:2000],
            status=PostStatus.RAW,
        )
        async with get_session() as session:
            session.add(post)
            await session.commit()
            await session.refresh(post)
            extractor = _get_extractor()
            post = await process_post(session, post, extractor)

        await ctx.send(
            f"Post ingested (ID: `{post.id[:8]}`). Status: `{post.status}`",
            ephemeral=True,
        )

    @submit_command.error
    async def submit_error(ctx: commands.Context, error):
        if isinstance(error, commands.MissingRole):
            await ctx.send("You need the Moderator role to use this command.", ephemeral=True)
        else:
            raise error

    return bot


async def _handle_discord_message(message: discord.Message) -> None:
    """Process a Discord message as a potential post."""

    platform_post_id = f"{message.channel.id}_{message.id}"

    async with get_session() as session:
        existing = (
            await session.exec(
                select(Post).where(
                    Post.platform == Platform.DISCORD,
                    Post.platform_post_id == platform_post_id,
                )
            )
        ).first()
        if existing:
            return

        post = Post(
            platform=Platform.DISCORD,
            platform_post_id=platform_post_id,
            platform_author_id=str(message.author.id),
            author_display_name=str(message.author.display_name),
            source_url=message.jump_url,
            source_community=f"Discord: {message.guild.name if message.guild else 'DM'}",
            title=message.content[:80],
            raw_text=message.content[:2000],
            status=PostStatus.RAW,
        )
        session.add(post)
        await session.commit()
        await session.refresh(post)

        extractor = _get_extractor()
        await process_post(session, post, extractor)


async def run_discord_bot() -> None:
    settings = get_settings()
    bot = create_bot()
    await bot.start(settings.discord_bot_token)
