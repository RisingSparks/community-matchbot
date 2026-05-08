"""Backfill deduplication fields and link existing duplicate posts.

Usage:
    uv run python scripts/backfill_dedup.py [--dry-run] [--window 30]
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

import typer
from datasketch import MinHash, MinHashLSH
from sqlmodel import or_, select

from matchbot.db.engine import get_session
from matchbot.db.models import Event, Post, PostStatus
from matchbot.extraction.dedup import (
    DEFAULT_NUM_PERM,
    compute_minhash,
    deserialize_minhash,
    generate_content_hash,
    get_dedup_text,
    serialize_minhash,
)

app = typer.Typer(add_completion=False)
logger = logging.getLogger("matchbot.backfill_dedup")


@app.command()
def main(
    dry_run: bool = typer.Option(False, help="Show updates without writing them."),
    window: int = typer.Option(30, help="Days to look back for duplicates."),
    threshold: float = typer.Option(0.7, help="Jaccard similarity threshold for fuzzy match."),
) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(_main_async(dry_run=dry_run, window_days=window, threshold=threshold))


async def _main_async(*, dry_run: bool, window_days: int, threshold: float) -> None:
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=window_days)

    async with get_session() as session:
        # 1. Fill missing hashes/sigs first
        posts_missing_sigs = (
            await session.exec(
                select(Post).where(
                    or_(Post.content_hash.is_(None), Post.minhash_sigs.is_(None)),
                    Post.detected_at >= cutoff,
                )
            )
        ).all()

        logger.info("Filling missing hashes/sigs for %d posts...", len(posts_missing_sigs))
        for post in posts_missing_sigs:
            dedup_text = get_dedup_text(post)
            if not dedup_text:
                continue
            if not post.content_hash:
                post.content_hash = generate_content_hash(dedup_text)
            if not post.minhash_sigs:
                m = compute_minhash(dedup_text)
                post.minhash_sigs = serialize_minhash(m)
            session.add(post)

        if not dry_run:
            await session.commit()
            logger.info("Hashes/sigs saved.")

        # 2. Re-fetch all posts ordered by detected_at to process them chronologically
        all_posts = (
            await session.exec(
                select(Post)
                .where(Post.detected_at >= cutoff)
                .order_by(Post.detected_at.asc())
            )
        ).all()

        processed_canonicals_by_id: dict[str, MinHash] = {}
        processed_hash_to_id: dict[str, str] = {}
        deduped_count = 0

        logger.info("Analyzing %d posts for duplicates...", len(all_posts))

        # Use a single in-memory index for this backfill window so lookups stay O(1).
        lsh = MinHashLSH(
            threshold=threshold * 0.8,
            num_perm=DEFAULT_NUM_PERM,
        )

        for post in all_posts:
            # If already has a parent, it was either processed by the new pipeline or
            # we are re-running this script. Count it as deduped but don't re-process.
            if post.parent_post_id:
                continue

            dedup_text = get_dedup_text(post)
            if not dedup_text:
                continue

            if not post.minhash_sigs:
                m_new = compute_minhash(dedup_text)
                post.minhash_sigs = serialize_minhash(m_new)
            else:
                m_new = deserialize_minhash(post.minhash_sigs)

            if not post.content_hash:
                post.content_hash = generate_content_hash(dedup_text)

            exact_parent_id = processed_hash_to_id.get(post.content_hash)

            fuzzy_parent_id = None
            if not exact_parent_id:
                candidates = lsh.query(m_new)
                for cand_id in candidates:
                    cand_minhash = processed_canonicals_by_id.get(cand_id)
                    if cand_minhash is None:
                        continue
                    if m_new.jaccard(cand_minhash) >= threshold:
                        fuzzy_parent_id = cand_id
                        break

            parent_id = exact_parent_id or fuzzy_parent_id

            if parent_id:
                logger.info(
                    "%s %s -> duplicate of %s",
                    "[dry-run]" if dry_run else "[dedup]",
                    post.id,
                    parent_id,
                )

                if not dry_run:
                    post.parent_post_id = parent_id
                    post.status = PostStatus.SKIPPED
                    post.skipped_reason = "duplicate"
                    session.add(post)
                    session.add(
                        Event(
                            event_type="post_deduplicated",
                            post_id=post.id,
                            actor="system",
                            payload=json.dumps({"parent_post_id": parent_id}),
                            note="Backfilled deduplication linkage.",
                        )
                    )
                deduped_count += 1
            else:
                # This is a new canonical post
                processed_canonicals_by_id[post.id] = m_new
                processed_hash_to_id[post.content_hash] = post.id
                lsh.insert(post.id, m_new)

        if not dry_run:
            await session.commit()
            logger.info("Changes committed.")

        logger.info("Summary:")
        logger.info("  Total posts scanned: %d", len(all_posts))
        logger.info("  Duplicates linked:  %d", deduped_count)
        logger.info("  Unique posts kept:   %d", len(processed_canonicals_by_id))


if __name__ == "__main__":
    app()
