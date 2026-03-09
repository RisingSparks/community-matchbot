"""Tests for Typer CLI commands against an in-memory database.

CLI commands call asyncio.run() internally, so test functions must be
synchronous. We seed data via a dedicated event loop separate from
the pytest-asyncio test runner.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from typer.testing import CliRunner

from matchbot.cli.app import app
from matchbot.db.models import Match, MatchStatus, Platform, Post, PostStatus, PostType

runner = CliRunner()


# ---------------------------------------------------------------------------
# Synchronous CLI test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cli_env():
    """
    Provides (session, factory, loop) for synchronous CLI tests.

    - session: AsyncSession backed by in-memory SQLite
    - factory: async context manager that yields the session (for patching)
    - loop: event loop to use for async setup/teardown
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    loop = asyncio.new_event_loop()

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    loop.run_until_complete(_setup())

    session = AsyncSession(engine, expire_on_commit=False)

    @asynccontextmanager
    async def factory():
        yield session

    yield session, factory, loop

    async def _cleanup():
        await session.close()
        await engine.dispose()

    loop.run_until_complete(_cleanup())
    loop.close()


def run_in(loop: asyncio.AbstractEventLoop, coro):
    """Run a coroutine in the given loop."""
    return loop.run_until_complete(coro)


# ---------------------------------------------------------------------------
# Queue tests
# ---------------------------------------------------------------------------


def test_queue_list_empty(cli_env):
    session, factory, loop = cli_env
    with patch("matchbot.cli._db.get_session", factory):
        result = runner.invoke(app, ["queue", "list"])
    assert result.exit_code == 0
    assert "No potential connections" in result.output


def test_queue_list_shows_matches(cli_env, seeker_post_factory, camp_post_factory):
    session, factory, loop = cli_env

    async def seed():
        seeker = seeker_post_factory()
        camp = camp_post_factory()
        session.add(seeker)
        session.add(camp)
        await session.commit()
        await session.refresh(seeker)
        await session.refresh(camp)

        match = Match(
            seeker_post_id=seeker.id,
            camp_post_id=camp.id,
            status=MatchStatus.PROPOSED,
            score=0.75,
        )
        session.add(match)
        await session.commit()
        await session.refresh(match)
        return match

    match = run_in(loop, seed())

    with patch("matchbot.cli._db.get_session", factory):
        result = runner.invoke(app, ["queue", "list"])
    assert result.exit_code == 0
    assert match.id[:8] in result.output


def test_queue_approve(cli_env, seeker_post_factory, camp_post_factory):
    session, factory, loop = cli_env

    async def seed():
        seeker = seeker_post_factory()
        camp = camp_post_factory()
        session.add(seeker)
        session.add(camp)
        await session.commit()
        await session.refresh(seeker)
        await session.refresh(camp)
        match = Match(
            seeker_post_id=seeker.id,
            camp_post_id=camp.id,
            status=MatchStatus.PROPOSED,
            score=0.75,
        )
        session.add(match)
        await session.commit()
        await session.refresh(match)
        return match

    match = run_in(loop, seed())

    with patch("matchbot.cli._db.get_session", factory):
        result = runner.invoke(app, ["queue", "approve", match.id])
    assert result.exit_code == 0, result.output
    assert "verified for intro" in result.output.lower()

    async def check():
        await session.refresh(match)
        return match.status

    assert run_in(loop, check()) == MatchStatus.APPROVED


def test_queue_reject(cli_env, seeker_post_factory, camp_post_factory):
    session, factory, loop = cli_env

    async def seed():
        seeker = seeker_post_factory()
        camp = camp_post_factory()
        session.add(seeker)
        session.add(camp)
        await session.commit()
        await session.refresh(seeker)
        await session.refresh(camp)
        match = Match(
            seeker_post_id=seeker.id,
            camp_post_id=camp.id,
            status=MatchStatus.PROPOSED,
            score=0.75,
        )
        session.add(match)
        await session.commit()
        await session.refresh(match)
        return match

    match = run_in(loop, seed())

    with patch("matchbot.cli._db.get_session", factory):
        result = runner.invoke(app, ["queue", "reject", match.id, "--reason", "Different years"])
    assert result.exit_code == 0, result.output
    assert "dismissed" in result.output.lower()

    async def check():
        await session.refresh(match)
        return match.status, match.mismatch_reason

    status, reason = run_in(loop, check())
    assert status == MatchStatus.DECLINED
    assert reason == "Different years"


def test_queue_view(cli_env, seeker_post_factory, camp_post_factory):
    session, factory, loop = cli_env

    async def seed():
        seeker = seeker_post_factory()
        camp = camp_post_factory()
        session.add(seeker)
        session.add(camp)
        await session.commit()
        await session.refresh(seeker)
        await session.refresh(camp)
        match = Match(
            seeker_post_id=seeker.id,
            camp_post_id=camp.id,
            status=MatchStatus.PROPOSED,
            score=0.75,
        )
        session.add(match)
        await session.commit()
        await session.refresh(match)
        return match

    match = run_in(loop, seed())

    with patch("matchbot.cli._db.get_session", factory):
        result = runner.invoke(app, ["queue", "view", match.id])
    assert result.exit_code == 0, result.output
    assert match.id[:8] in result.output


def test_queue_view_labels_infra_matches(cli_env):
    session, factory, loop = cli_env

    async def seed():
        seeking = Post(
            platform=Platform.REDDIT,
            platform_post_id="infra_seek",
            platform_author_id="infra_seek",
            title="Need generator",
            raw_text="Seeking power for build week",
            status=PostStatus.INDEXED,
            post_type=PostType.INFRASTRUCTURE,
            infra_role="seeking",
            infra_categories="power",
        )
        offering = Post(
            platform=Platform.REDDIT,
            platform_post_id="infra_offer",
            platform_author_id="infra_offer",
            title="Offering generator",
            raw_text="Offering power support",
            status=PostStatus.INDEXED,
            post_type=PostType.INFRASTRUCTURE,
            infra_role="offering",
            infra_categories="power",
        )
        session.add(seeking)
        session.add(offering)
        await session.commit()
        await session.refresh(seeking)
        await session.refresh(offering)
        match = Match(
            seeker_post_id=seeking.id,
            camp_post_id=offering.id,
            status=MatchStatus.PROPOSED,
            score=0.75,
        )
        session.add(match)
        await session.commit()
        await session.refresh(match)
        return match

    match = run_in(loop, seed())

    with patch("matchbot.cli._db.get_session", factory):
        result = runner.invoke(app, ["queue", "view", match.id])
    assert result.exit_code == 0, result.output
    assert "SEEKING" in result.output
    assert "OFFERING" in result.output


def test_queue_send_intro_dry_run(cli_env, seeker_post_factory, camp_post_factory):
    session, factory, loop = cli_env

    async def seed():
        seeker = seeker_post_factory(vibes=["art"], contribution_types=["build"])
        camp = camp_post_factory(vibes=["art"], contribution_types=["build"])
        session.add(seeker)
        session.add(camp)
        await session.commit()
        await session.refresh(seeker)
        await session.refresh(camp)
        match = Match(
            seeker_post_id=seeker.id,
            camp_post_id=camp.id,
            status=MatchStatus.APPROVED,
            score=0.80,
        )
        session.add(match)
        await session.commit()
        await session.refresh(match)
        return match

    match = run_in(loop, seed())

    with patch("matchbot.cli._db.get_session", factory):
        result = runner.invoke(
            app,
            ["queue", "send-intro", match.id, "--platform", "reddit", "--dry-run"],
        )
    assert result.exit_code == 0, result.output
    assert "dry-run" in result.output.lower()

    async def check():
        await session.refresh(match)
        return match.status

    assert run_in(loop, check()) == MatchStatus.APPROVED  # unchanged


# ---------------------------------------------------------------------------
# Posts tests
# ---------------------------------------------------------------------------


def test_posts_list_empty(cli_env):
    session, factory, loop = cli_env
    with patch("matchbot.cli._db.get_session", factory):
        result = runner.invoke(app, ["posts", "list"])
    assert result.exit_code == 0
    assert "No signals found" in result.output


def test_posts_list_shows_posts(cli_env, seeker_post_factory):
    session, factory, loop = cli_env

    async def seed():
        post = seeker_post_factory()
        session.add(post)
        await session.commit()
        await session.refresh(post)
        return post

    post = run_in(loop, seed())

    with patch("matchbot.cli._db.get_session", factory):
        result = runner.invoke(app, ["posts", "list"])
    assert result.exit_code == 0, result.output
    assert post.id[:8] in result.output


def test_posts_show(cli_env, seeker_post_factory):
    session, factory, loop = cli_env

    async def seed():
        post = seeker_post_factory()
        session.add(post)
        await session.commit()
        await session.refresh(post)
        return post

    post = run_in(loop, seed())

    with patch("matchbot.cli._db.get_session", factory):
        result = runner.invoke(app, ["posts", "show", post.id])
    assert result.exit_code == 0, result.output
    assert post.title[:20] in result.output


def test_posts_re_extract_many(cli_env):
    session, factory, loop = cli_env

    async def seed():
        first = Post(
            platform=Platform.REDDIT,
            platform_post_id="batch_1",
            platform_author_id="fearless_dp",
            author_display_name="fearless_dp",
            title="First recruiting post",
            raw_text="We are building a camp and need people.",
            status=PostStatus.INDEXED,
            post_type=PostType.MENTORSHIP,
            role="seeker",
        )
        second = Post(
            platform=Platform.REDDIT,
            platform_post_id="batch_2",
            platform_author_id="fearless_dp",
            author_display_name="fearless_dp",
            title="Second recruiting post",
            raw_text="Looking for more builders.",
            status=PostStatus.INDEXED,
            post_type=PostType.MENTORSHIP,
            role="seeker",
        )
        session.add(first)
        session.add(second)
        await session.commit()

    run_in(loop, seed())

    async def fake_process_post(db_session, post, extractor):
        post.status = PostStatus.INDEXED
        post.role = "camp"
        db_session.add(post)
        await db_session.commit()
        await db_session.refresh(post)
        return post

    extractor = MagicMock()
    extractor.aclose = AsyncMock(return_value=None)

    with (
        patch("matchbot.cli._db.get_session", factory),
        patch("matchbot.cli.cmd_posts._build_extractor", return_value=extractor),
        patch("matchbot.extraction.process_post", side_effect=fake_process_post),
    ):
        result = runner.invoke(
            app,
            [
                "posts",
                "re-extract-many",
                "--author",
                "fearless_dp",
                "--role",
                "seeker",
                "--limit",
                "10",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Re-analyzed 2 signal(s)." in result.output

    async def check():
        rows = (
            await session.exec(
                select(Post).where(Post.author_display_name == "fearless_dp").order_by(Post.platform_post_id)
            )
        ).all()
        return [(row.status, row.role) for row in rows]

    assert run_in(loop, check()) == [
        (PostStatus.INDEXED, "camp"),
        (PostStatus.INDEXED, "camp"),
    ]


# ---------------------------------------------------------------------------
# Report tests
# ---------------------------------------------------------------------------


def test_report_metrics_json(cli_env, tmp_path):
    session, factory, loop = cli_env
    out = str(tmp_path / "metrics.json")
    with patch("matchbot.cli._db.get_session", factory):
        result = runner.invoke(app, ["report", "metrics", "--format", "json", "--output", out])
    assert result.exit_code == 0, result.output
    assert Path(out).exists()
    data = json.loads(Path(out).read_text())
    assert "active_camp_profiles" in data
    assert "intro_to_conversation_rate" in data


def test_report_metrics_stdout(cli_env):
    session, factory, loop = cli_env
    with patch("matchbot.cli._db.get_session", factory):
        result = runner.invoke(app, ["report", "metrics"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "total_posts_indexed" in data


def test_report_weekly(cli_env):
    session, factory, loop = cli_env
    with patch("matchbot.cli._db.get_session", factory):
        result = runner.invoke(app, ["report", "weekly", "--week", "2025-W34"])
    assert result.exit_code == 0, result.output
    assert "Weekly Report" in result.output
