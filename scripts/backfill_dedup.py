"""Backfill deduplication fields and link existing duplicate posts.

Usage:
    uv run python scripts/backfill_dedup.py [--dry-run] [--window 30]
"""

from __future__ import annotations

import asyncio
import json
import logging

import typer
from datasketch import MinHashLSH
from sqlmodel import or_, select

from matchbot.db.engine import get_session
from matchbot.db.models import Event, Post, PostStatus
from matchbot.extraction.dedup import (
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
    threshold: float = typer.Option(0.7, help="Jaccard similarity threshold for fuzzy match.")
) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(_main_async(dry_run=dry_run, window_days=window, threshold=threshold))


async def _main_async(*, dry_run: bool, window_days: int, threshold: float) -> None:
    async with get_session() as session:
        # 1. Fill missing hashes/sigs first
        posts_missing_sigs = (
            await session.exec(
                select(Post).where(
                    or_(Post.content_hash.is_(None), Post.minhash_sigs.is_(None)),
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
        all_posts = (await session.exec(select(Post).order_by(Post.detected_at.asc()))).all()

        processed_canonicals = [] # List of (id, content_hash, minhash_obj)
        deduped_count = 0

        logger.info("Analyzing %d posts for duplicates...", len(all_posts))
        
        # We'll use a sliding window for fuzzy match to avoid memory bloat if DB is huge,
        # but for backfill we might just want to check against all previous if it's small enough.
        # Let's use LSH for performance.
        lsh = MinHashLSH(
            threshold=threshold * 0.8,
            num_perm=128,
        )  # Slightly lower threshold for LSH recall

        for post in all_posts:
            # If already has a parent, it was either processed by the new pipeline or 
            # we are re-running this script. Count it as deduped but don't re-process.
            if post.parent_post_id:
                # Add to LSH if it's not actually the parent (shouldn't happen with detected_at.asc)
                continue

            dedup_text = get_dedup_text(post)
            if not dedup_text:
                continue

            m_new = deserialize_minhash(post.minhash_sigs)
            
            # Check Exact Match
            exact_parent = next(
                (p for p in processed_canonicals if p["hash"] == post.content_hash),
                None,
            )
            
            # Check Fuzzy Match via LSH
            fuzzy_parent_id = None
            if not exact_parent:
                candidates = lsh.query(m_new)
                # Verify candidates
                for cand_id in candidates:
                    cand_meta = next(p for p in processed_canonicals if p['id'] == cand_id)
                    if m_new.jaccard(cand_meta['minhash']) >= threshold:
                        fuzzy_parent_id = cand_id
                        break
            
            parent_id = exact_parent['id'] if exact_parent else fuzzy_parent_id
            
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
                processed_canonicals.append(
                    {
                        "id": post.id,
                        "hash": post.content_hash,
                        "minhash": m_new,
                    }
                )
                lsh.insert(post.id, m_new)

        if not dry_run:
            await session.commit()
            logger.info("Changes committed.")

        logger.info("Summary:")
        logger.info("  Total posts scanned: %d", len(all_posts))
        logger.info("  Duplicates linked:  %d", deduped_count)
        logger.info("  Unique posts kept:   %d", len(processed_canonicals))


if __name__ == "__main__":
    app()
