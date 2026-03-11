"""Backfill missing infrastructure roles from post text.

Usage:
    uv run python scripts/backfill_infra_roles.py [--dry-run]
"""

from __future__ import annotations

import asyncio
import json
import logging

import typer
from sqlmodel import select

from matchbot.db.engine import get_session
from matchbot.db.models import Event, Post, PostType
from matchbot.extraction.keywords import keyword_filter

app = typer.Typer(add_completion=False)
logger = logging.getLogger("matchbot.backfill_infra_roles")


def _infer_infra_role(title: str, raw_text: str) -> str | None:
    kw_result = keyword_filter(title, raw_text)
    if kw_result.post_type == PostType.INFRASTRUCTURE:
        return kw_result.infra_role
    return None


@app.command()
def main(dry_run: bool = typer.Option(False, help="Show updates without writing them.")) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(_main_async(dry_run=dry_run))


async def _main_async(*, dry_run: bool) -> None:
    async with get_session() as session:
        posts = (
            await session.exec(
                select(Post).where(
                    Post.post_type == PostType.INFRASTRUCTURE,
                    Post.infra_role.is_(None),
                )
            )
        ).all()

        updated = 0
        skipped = 0

        for post in posts:
            inferred_role = _infer_infra_role(post.title or "", post.raw_text or "")
            if inferred_role is None:
                skipped += 1
                continue

            logger.info(
                "%s %s -> %s",
                "[dry-run]" if dry_run else "[update]",
                post.id,
                inferred_role,
            )

            if dry_run:
                updated += 1
                continue

            post.infra_role = inferred_role
            session.add(post)
            session.add(
                Event(
                    event_type="infra_role_backfilled",
                    post_id=post.id,
                    actor="system",
                    payload=json.dumps({"infra_role": inferred_role}),
                    note="Backfilled missing infra_role from keyword inference.",
                )
            )
            updated += 1

        if not dry_run:
            await session.commit()

        logger.info("Processed %d infra posts with missing role", len(posts))
        logger.info("Updated %d posts", updated)
        logger.info("Skipped %d posts", skipped)


if __name__ == "__main__":
    app()
